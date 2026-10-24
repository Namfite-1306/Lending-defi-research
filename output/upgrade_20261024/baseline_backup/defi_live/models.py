import csv,json,time,tempfile,threading
from pathlib import Path
from decimal import Decimal
from collections import Counter,defaultdict
from defi_data.rpc import Rpc
from defi_data.pipeline import CONTRACTS,call_request,registry
from defi_data.evm import words,uint
from defi_data.expansion import aave_positions
from defi_data.recovery_recursive import motifs
from defi_models.core import Portfolio,DEFAULTS,clean,concentration,stamp
from defi_models.analyses import rq1
from defi_models.simulation import rq6,rq7
from .exposures import exposures

class SnapshotData:
    def __init__(self,p,scope):self.p=p;self.scope=scope
    def snapshot(self):return self.p,self.scope

class LiveModels:
    def __init__(self,store,wallet_limit=10,wallet_file=None,historical_results=None):
        self.store=store;self.wallet_limit=wallet_limit;self.wallet_file=wallet_file;self.historical_results=Path(historical_results) if historical_results else None
        self.rpc=Rpc(store.folder/'rpc_cache',batch_size=100,multicall=True,cache_individual=False,use_cache=False,timeout=20,retry_attempts=2)
        self.exposure_rpc=Rpc(store.folder/'rpc_cache',batch_size=100,multicall=True,cache_individual=False,use_cache=False,timeout=10,retry_attempts=1)
    def wallet_list(self):
        if self.wallet_file:
            raw=Path(self.wallet_file).read_text(encoding='utf8').splitlines();wallets=sorted(set(a.strip().lower() for a in raw if a.strip()))
            import re
            if not all(re.fullmatch('0x[0-9a-f]{40}',a) for a in wallets):raise ValueError('Invalid monitored wallet address')
            source='explicit_wallet_list'
        else:
            with self.store.db() as c:wallets=[r[0] for r in c.execute("SELECT account FROM events WHERE protocol='aave_v3' AND name='Borrow' AND account<>'' GROUP BY account ORDER BY max(block) DESC,account LIMIT 10000")]
            source='recent_Borrow_in_live_tail; not representative full universe'
        return (wallets[:self.wallet_limit] if self.wallet_limit else wallets),source
    def update(self):
        block=self.store.meta('cursor')
        if block is None:return
        h=self.store.header(block);wallets,selection=self.wallet_list()
        if not wallets:raise ValueError('No monitored wallets yet; wait for Borrow events or pass --wallet-file')
        pool=CONTRACTS['aave_v3'][0]
        accounts=self.rpc.many([call_request(pool,'getUserAccountData(address)',[a],block) for a in wallets])
        active=[a for a,r in zip(wallets,accounts) if uint(words(r)[1])>0]
        scope={'block':block,'block_hash':h['hash'],'source_stamp':h['stamp'],'monitored_wallets':len(wallets),'active_debt_wallets':len(active),
               'selection':selection,'full_universe':False,'timing':'current confirmed block-end snapshot; not pre-transaction state'}
        if not active:
            _,oracle,_=registry(self.rpc,block)
            self.store.publish('position_rows',block,h['hash'],h['stamp'],{'wallets':wallets,'positions':[],'oracle':oracle})
            self.store.publish('models',block,h['hash'],h['stamp'],{'scope':scope,'status':'no_active_monitored_aave_debt','rq1':None,'rq6':None,'rq7':None,'positions':[]})
            return
        modes=self.rpc.many([call_request(pool,'getUserEMode(address)',[a],block) for a in active])
        with tempfile.TemporaryDirectory(dir=self.store.folder) as directory:
            folder=Path(directory);snapshot=aave_positions(self.rpc,block,[(a,uint(words(m)[0])) for a,m in zip(active,modes)],out=folder)
            checks=snapshot['checks']
            if not checks or not all(r['passed'] for r in checks):raise ValueError('Live position validation did not pass')
            positions=[]
            for r in snapshot['positions']:
                positions.append(dict(r,block=block,token=r['token_address'],effective_lt=r['effective_liquidation_threshold']))
            p=Portfolio(positions,DEFAULTS);actual,_=p.stress();reported={r['account']:Decimal(r['hf_reported']) for r in checks}
            if any(abs(Decimal(str(v))-reported[a])/max(abs(reported[a]),Decimal('1e-12'))>Decimal('.0001') for a,v in zip(p.accounts,actual)):
                raise ValueError('Live model baseline HF does not match on-chain HF')
            self.store.publish('position_rows',block,h['hash'],h['stamp'],{'wallets':wallets,'positions':positions,'oracle':snapshot['scope']['oracle']})
            cfg=dict(DEFAULTS,shock_step=.05,shock_max=.6,max_rounds=50);data=SnapshotData(p,scope);payload={'scope':scope,'status':'validated_monitored_sample','rq1':None,'rq6':None,'rq7':None}
            for name,fn,filename in [('rq1',rq1,'stress_curve.csv'),('rq6',rq6,'cascade_scenarios.csv'),('rq7',rq7,'policy_grid.csv')]:
                dest=folder/name;dest.mkdir();result=fn(data,dest,cfg)
                with (dest/filename).open(encoding='utf-8-sig',newline='') as f:table=list(csv.DictReader(f))
                payload[name]={'summary':result,'table':table,'model_type':'counterfactual_simulation; not observed liquidations'}
            payload['positions']=[{'account':r['account'],'hf':r['hf_reported'],'debt_usd':r['reported_debt_usd'],'emode':r['emode']} for r in checks]
            payload['assumptions']={k:cfg[k] for k in ['liquidity_depth_usd','impact_coefficient','close_factor','liquidation_bonus','gas_usd','max_rounds']}
            # Ensure the snapshot still belongs to the canonical branch at publish time.
            fresh=self.rpc.one('eth_getBlockByNumber',[hex(block),False],cache=False)
            if fresh['hash']!=h['hash']:raise ValueError('Snapshot invalidated by reorg before publication')
            self.store.publish('models',block,h['hash'],h['stamp'],clean(payload))
    def update_exposures(self):
        source=self.store.product('position_rows')
        if not source:return
        current=self.store.product('exposures')
        if current and current['hash']==source['hash']:return
        p=source['payload'];result=exposures(self.exposure_rpc,self.store,p['wallets'],source['block'],p['positions'],p['oracle'])
        self.store.publish('exposures',source['block'],source['hash'],source['source_stamp'],result)
    def online_analytics(self,seconds=86400):
        cursor=self.store.meta('cursor')
        if cursor is None:return {'state':'warming_up'}
        h=self.store.header(cursor);start=self.store.meta('start_block');anchor=self.store.header(start-1);lower=max(anchor['stamp']+1,h['stamp']-seconds)
        es=self.store.events(lower,20001,until=h['stamp']);capped=len(es)>20000;es=es[:20000]
        liqs=[e for e in es if e['name'] in ['LiquidationCall','AbsorbDebt','Liquidate']]
        rq2=[]
        for protocol in CONTRACTS:
            weights=self.store.liquidation_groups(lower,h['stamp'],protocol)
            rq2.append({'protocol':protocol,**concentration(weights.values()),'unit':'liquidation event counts; not USD'})
        motif_counts={};aave=defaultdict(list)
        motif_lower=max(anchor['stamp']+1,h['stamp']-48*3600)
        motif_events=self.store.events(motif_lower,20001,protocol='aave_v3',until=h['stamp']);motif_capped=len(motif_events)>20000
        for e in motif_events[:20000]:
            if e['protocol']=='aave_v3' and e['name'] in ['Borrow','Supply']:
                aave[e['account']].append(dict(e,txidx=0))
        # idx is global log index within block, sufficient to preserve transaction order.
        for hours in [6,24,48]:
            count=0
            for events in aave.values():
                events.sort(key=lambda e:(e['block'],e['idx']));count+=sum(1 for _ in motifs(events,hours,h['stamp']))
            motif_counts[str(hours)]=count
        activity=Counter((e['account'],e['protocol']) for e in es if e['account']);network=[{'wallet':a,'protocol':p,'events':n,'edge_type':'activity_not_exposure'} for (a,p),n in activity.most_common(100)]
        rq4={'status':'needs_trained_parameters','interpretation':'no live causal self-excitation estimate'}
        if self.historical_results and (self.historical_results/'rq4/summary.json').exists():
            source=json.loads((self.historical_results/'rq4/summary.json').read_text(encoding='utf8'));fit=source.get('hawkes');protocol=source.get('protocol','aave_v3')
            if fit:
                import math
                valid=all(math.isfinite(float(fit[k])) for k in ['beta_per_hour','branching_ratio','baseline_per_hour','half_life_hours'])
                valid=valid and float(fit['beta_per_hour'])>0 and 0<=float(fit['branching_ratio'])<1 and float(fit['baseline_per_hour'])>0 and float(fit['half_life_hours'])>0
                valid=valid and fit.get('converged') is True and protocol in CONTRACTS and source.get('train_end_utc') and stamp(source['train_end_utc'])<=h['stamp']
                if not valid:fit=None;rq4={'status':'parameters_invalid_or_trained_in_future','interpretation':'model not applied to live observations'}
            if fit:
                import math
                beta=float(fit['beta_per_hour']);eta=float(fit['branching_ratio']);mu=float(fit['baseline_per_hour'])
                excitation=sum(math.exp(-beta*(h['stamp']-e['stamp'])/3600) for e in liqs if e['protocol']==protocol)
                warm_hours=10*float(fit['half_life_hours'])
                rq4={'status':'conditional_live_intensity' if (h['stamp']-lower)/3600>=warm_hours and not capped else 'warming_up',
                     'protocol':protocol,'intensity_events_per_hour':mu+eta*beta*excitation,'training_cutoff':source.get('train_end_utc'),
                     'parameter_source':'historical model; not automatically retrained','required_warmup_hours':warm_hours,
                     'interpretation':'conditional Hawkes intensity, not guaranteed future liquidation count'}
        return clean({'state':'available','source_block':cursor,'source_stamp':h['stamp'],'observed_from':lower,'observed_seconds':h['stamp']-lower,
          'requested_window_seconds':seconds,'history_contiguous_with_research':False,'capped_at_20000_events':capped,
          'rq2':rq2,'rq3':{'temporal_motifs_by_hours':motif_counts,'verified_recursive':False,'window_context_complete':h['stamp']-motif_lower>=48*3600-1 and not motif_capped,'capped':motif_capped,'matched_causal_effect':'historical research only'},
          'rq4':rq4,'rq5':{'edges':network,'scope':'live activity; current partial valued exposure is in /api/models payload.rq5; no causal contagion estimate'}})

def model_loop(models,stop,interval):
    while not stop.is_set():
        models.store.set_meta('model_job',{'state':'running','started_at':time.time()})
        try:
            models.update();models.store.set_meta('model_job',{'state':'idle','finished_at':time.time()})
        except Exception as e:
            models.store.set_meta('model_job',{'state':'error','error':str(e)[:220],'error_at':time.time()})
        stop.wait(interval if models.store.product('models') else min(interval,10))

def exposure_loop(models,stop,interval):
    while not stop.is_set():
        try:
            models.update_exposures();models.store.set_meta('exposure_error',None)
        except Exception as e:models.store.set_meta('exposure_error',{'kind':getattr(e,'kind',type(e).__name__),'at':time.time()})
        stop.wait(interval if models.store.product('position_rows') else 2)
