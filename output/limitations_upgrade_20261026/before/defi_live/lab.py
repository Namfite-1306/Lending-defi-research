"""Interactive research views and bounded, in-memory what-if jobs."""
import csv
import json
import math
import threading
import time
import uuid
from pathlib import Path
import numpy as np
from defi_models.__main__ import config, preflight
from defi_models.core import Data, Portfolio, clean, require
from defi_models.rq6 import cascade


class LabBusy(ValueError):pass


class ResearchLab:
    LIMITS={'shock':(0,.6),'lt_shift':(-.1,.1),'close_factor':(.05,1),
            'liquidation_bonus':(0,.2),'liquidity_depth_usd':(100000,1e10),
            'impact_coefficient':(0,.2),'gas_usd':(0,1000),'max_rounds':(1,200)}

    def __init__(self,store,models,source_stale_seconds=600):
        self.store=store;self.models=models;self.lock=threading.Lock()
        self.source_stale_seconds=source_stale_seconds
        self.history_lock=threading.Lock();self.history=None;self.jobs={};self.busy=False

    def historical(self):
        with self.history_lock:
            if self.history is not None:return self.history
            path=getattr(self.models,'historical_results',None)
            require(isinstance(path,(str,Path)),'Chưa cấu hình bộ kết quả lịch sử. Dùng --historical-results.')
            run=Path(path);manifest=json.loads((run/'manifest.json').read_text(encoding='utf8'))
            require(manifest.get('all_executed') and manifest.get('mode')=='research_run','Cần một research run hoàn tất, không dùng smoke.')
            require({r['rq'] for r in manifest['models'] if r['execution']=='completed'}==set(range(1,8)),'Research Lab cần bộ kết quả đủ 7 RQ.')
            cfg=config(run/'config.json');dataset=Path(manifest['data_run'])
            gate=preflight(dataset,cfg)
            require(gate['passed'],'Dataset không qua gate: '+'; '.join(gate['errors']))
            data=Data(dataset,cfg);portfolio,scope=data.snapshot()
            result={'config':cfg,'scope':scope,'run_name':run.name,'versions':manifest['versions'],
                    'mode':'historical_fixed','rq':{},'source_integrity':'frozen inputs verified; saved outputs are read from selected run'}
            for n in range(1,8):
                folder=run/f'rq{n}';item={'summary':json.loads((folder/'summary.json').read_text(encoding='utf8')),'tables':{}}
                for p in folder.glob('*.csv'):
                    with p.open(encoding='utf-8-sig',newline='') as handle:item['tables'][p.stem]=list(csv.DictReader(handle))
                result['rq'][str(n)]=item
            self.history=(portfolio,scope,cfg,clean(result))
            return self.history

    def data(self):
        return self.historical()[3]

    def parameters(self,request):
        require(isinstance(request,dict),'Yêu cầu phải là JSON object.')
        allowed=set(self.LIMITS)|{'source','factor'}
        require(not set(request)-allowed,'Có tham số không được hỗ trợ.')
        require(request.get('source') in ('historical','live'),'Chọn historical hoặc live.')
        require(request.get('factor','joint') in ('joint','eth','btc'),'Factor không hợp lệ.')
        defaults=dict(shock=.2,lt_shift=0.,close_factor=.5,liquidation_bonus=.05,
                      liquidity_depth_usd=100000000.,impact_coefficient=.05,gas_usd=20.,max_rounds=100)
        values={**defaults,**request}
        for key,(lower,upper) in self.LIMITS.items():
            value=values[key]
            require(isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and lower<=value<=upper,f'{key} phải nằm trong [{lower}, {upper}].')
        require(isinstance(values['max_rounds'],int),'max_rounds phải là số nguyên.')
        values.setdefault('factor','joint')
        return values

    def submit(self,request):
        values=self.parameters(request)
        with self.lock:
            if self.busy:raise LabBusy('Đang tính một kịch bản khác. Vui lòng đợi hoàn tất.')
            self.busy=True;identifier=uuid.uuid4().hex
            self.jobs[identifier]={'id':identifier,'state':'running','submitted_at':time.time(),'parameters':values}
            while len(self.jobs)>8:self.jobs.pop(next(iter(self.jobs)))
        threading.Thread(target=self.calculate,args=(identifier,values),daemon=True,name='interactive-scenario').start()
        return {'id':identifier,'state':'running'}

    def job(self,identifier):
        with self.lock:
            require(identifier in self.jobs,'Kịch bản không tồn tại hoặc đã hết phiên.')
            return dict(self.jobs[identifier])

    def calculate(self,identifier,values):
        try:
            if values['source']=='historical':
                portfolio,scope,cfg,_=self.historical();cfg=dict(cfg)
                provenance={'mode':'historical_counterfactual','block':scope['block'],'wallets':len(portfolio.accounts)}
            else:
                source=self.store.product('position_rows')
                require(source and source['payload'].get('positions'),'Chưa có snapshot live hợp lệ. Có thể dùng snapshot lịch sử trong lúc collector cập nhật.')
                from defi_models.core import DEFAULTS
                cfg=dict(DEFAULTS);portfolio=Portfolio(source['payload']['positions'],cfg)
                head=self.store.meta('head');now=time.time()
                clock=head['stamp']+max(0,now-head['observed_at']) if head else now
                source_age=max(0,clock-source['source_stamp'])
                source_state='source_error' if self.store.meta('collector_status',{}).get('state')=='error' else 'stale' if source_age>self.source_stale_seconds else 'within_update_window'
                provenance={'mode':'live_cohort_counterfactual','block':source['block'],'block_hash':source['hash'],
                            'source_stamp':source['source_stamp'],'source_age_seconds_at_calculation':round(source_age,1),
                            'source_state':source_state,'wallets':len(portfolio.accounts),'full_universe':False}
            cfg.update({k:values[k] for k in ('close_factor','liquidation_bonus','liquidity_depth_usd','impact_coefficient','gas_usd','max_rounds')})
            factor=values['factor'];shock=values['shock'];shift=values['lt_shift']
            e=shock if factor!='btc' else 0.;b=shock if factor!='eth' else 0.
            hf,debt=portfolio.stress(e,b,shift);baseline,_=portfolio.stress();eligible=(hf<1)&(debt>0)
            indexes=np.flatnonzero(eligible);indexes=indexes[np.argsort(-debt[indexes],kind='stable')]
            positions=[dict(wallet=portfolio.accounts[i],hf=float(hf[i]),debt_usd=float(debt[i]),
                            baseline_hf=float(baseline[i])) for i in indexes[:100]]
            curve=[]
            for s in np.linspace(0,.6,13):
                h,d=portfolio.stress(s if factor!='btc' else 0,s if factor!='eth' else 0,shift)
                curve.append(dict(shock_fraction=float(s),eligible_wallets=int(((h<1)&(d>0)).sum()),eligible_risk_debt_usd=float(d[h<1].sum())))
            result,rounds=cascade(portfolio,shock,cfg,lt_shift=shift)
            control,control_rounds=cascade(portfolio,shock,dict(cfg,impact_coefficient=0),lt_shift=shift)
            if values['source']=='live':
                header=self.store.header(source['block'])
                require(header and header['hash']==source['hash'],'Snapshot live đã bị reorg; hãy tính lại.')
            payload=clean(dict(provenance=provenance,parameters=values,
                stress=dict(eligible_wallets=int(eligible.sum()),newly_eligible_wallets=int((eligible&(baseline>=1)).sum()),
                            eligible_debt_usd=float(debt[eligible].sum()),total_debt_usd=float(debt.sum()),curve=curve,
                            positions=positions,positions_total=int(eligible.sum())),
                cascade=result,control=control,rounds=rounds,control_rounds=control_rounds,
                assumptions='RQ1 uses the selected factor. Cascade shocks ETH and BTC jointly at the selected shock. Fixed snapshot, uncalibrated impact; not on-chain bad debt.'))
            with self.lock:self.jobs[identifier].update(state='completed',result=payload,finished_at=time.time())
        except Exception as exc:
            with self.lock:self.jobs[identifier].update(state='failed',error=str(exc)[:300],finished_at=time.time())
        finally:
            with self.lock:self.busy=False
