"""Read-only adapters and assumption calculations for the Streamlit dashboard."""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from .available_rq14 import sample_portfolio
from .core import DEFAULTS, ROOT, require, sha


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def discover_runs(root=ROOT/'results'):
    found={1:[],4:[]}
    if not Path(root).is_dir():return found
    for manifest_path in Path(root).rglob('manifest.json'):
        try:
            manifest=read_json(manifest_path)
            for rq in found:
                folder=manifest_path.parent/f'rq{rq}'
                required=['stress_curve.csv','factor_mapping.csv'] if rq==1 else ['hourly_counts.csv','hawkes_candidates.csv']
                complete=any(r.get('rq')==rq and r.get('execution')=='completed' for r in manifest.get('models',[]))
                if complete and (folder/'summary.json').is_file() and all((folder/p).is_file() for p in required):
                    found[rq].append(manifest_path.parent)
        except (OSError,ValueError,TypeError,AttributeError):continue
    for rq in found:found[rq].sort(key=lambda p:p.stat().st_mtime_ns,reverse=True)
    return found


def fingerprint(paths):
    return tuple((str(p),p.stat().st_mtime_ns,p.stat().st_size) for p in map(Path,paths))


def read_run(run,rq):
    run=Path(run);manifest=read_json(run/'manifest.json');folder=run/f'rq{rq}'
    result={'manifest':manifest,'summary':read_json(folder/'summary.json'),'path':str(run)}
    names=['stress_curve','factor_mapping'] if rq==1 else ['hourly_counts','hawkes_candidates']
    for name in names:result[name]=pd.read_csv(folder/f'{name}.csv')
    if rq==4:
        panel=result['hourly_counts']
        panel['hour_utc']=pd.to_datetime(panel['hour_utc'],utc=True)
        require(not panel.empty and not panel['hour_utc'].duplicated().any(),'Hourly panel is empty or has duplicates')
        require((panel['hour_utc'].diff().dropna()==pd.Timedelta(hours=1)).all(),'Hourly panel is not continuous')
        require(np.isfinite(panel['liquidation_events']).all() and (panel['liquidation_events']>=0).all(),'Invalid hourly counts')
        require((panel['liquidation_events']%1==0).all(),'Fractional liquidation counts')
        require(int(panel['liquidation_events'].sum())==int(result['summary']['events']),'Panel/event count does not reconcile')
    return result


def validated_portfolio(run,derivatives=True):
    """Reconcile unchanged source files before enabling new what-if calculations."""
    manifest=read_json(Path(run)/'manifest.json')
    required={'positions_point_in_time_sample.csv','position_checks.csv','historical_reserve_config_sample.csv','position_scope.json'}
    sources={Path(r['path']).name:r for r in manifest.get('source_files',[]) if Path(r['path']).name in required}
    require(set(sources)==required,'This run has no validated sample sources for interactive RQ1')
    paths=[Path(r['path']).resolve() for r in sources.values()]
    require(all(p.is_relative_to(ROOT.resolve()) for p in paths),'Source files must stay in this project')
    require(len({p.parent for p in paths})==1,'Sample sources do not share a directory')
    for r in sources.values():
        path=Path(r['path'])
        require(path.is_file() and sha(path)==r['sha256'],f'Source file changed or missing: {path.name}')
    cfg={**DEFAULTS,**manifest.get('config',{})}
    if not derivatives:
        cfg['eth_symbols']=['WETH'];cfg['btc_symbols']=['WBTC']
    p,scope,_=sample_portfolio(paths[0].parent.parent,cfg)
    return p,scope


def stress_view(portfolio,eth,btc,lt_shift=0):
    require(math.isfinite(lt_shift) and -.1<=lt_shift<=.1,'LT shift must be between -10 and +10 percentage points')
    baseline,_=portfolio.stress();hf,debt=portfolio.stress(eth,btc,lt_shift)
    eligible=(hf<1)&(debt>0)
    wallets=pd.DataFrame({
        'Ví':portfolio.accounts,'HF ban đầu':baseline,'HF kịch bản':hf,
        'Dư nợ ban đầu (USD)':portfolio.d.sum(axis=1),'Dư nợ kịch bản (USD)':debt,
        'Thế chấp kịch bản (USD)':(portfolio.c*portfolio.factors(eth,btc)).sum(axis=1),
        'Đủ điều kiện thanh lý':eligible,
    })
    total=float(debt.sum());at_risk=float(debt[eligible].sum())
    return {'wallets':wallets,'eligible_wallets':int(eligible.sum()),
            'newly_eligible_wallets':int((eligible&(baseline>=1)).sum()),'eligible_debt':at_risk,
            'total_debt':total,'debt_share':at_risk/total if total else 0}


def stress_curves(portfolio,lt_shift=0):
    result=[]
    for label in ['ETH','BTC','ETH + BTC']:
        for shock in np.linspace(0,.6,61):
            hf,debt=portfolio.stress(shock if label!='BTC' else 0,shock if label!='ETH' else 0,lt_shift)
            result.append({'Giảm giá (%)':round(float(shock)*100),'Kịch bản':label,
                           'Dư nợ đủ điều kiện (USD)':float(debt[(hf<1)&(debt>0)].sum())})
    return pd.DataFrame(result)


def aggregate_counts(panel,start,end,frequency='D'):
    require(frequency in ('D','W-MON','MS'),'Unsupported display frequency')
    # End is an inclusive calendar date; never create observations outside source rows.
    begin=pd.Timestamp(start,tz='UTC');finish=pd.Timestamp(end,tz='UTC')+pd.Timedelta(days=1)
    require(begin<finish,'Invalid date interval')
    selected=panel.loc[(panel.hour_utc>=begin)&(panel.hour_utc<finish)]
    if selected.empty:return pd.DataFrame(columns=['Thời gian UTC','Số thanh lý','Giờ quan sát'])
    values=selected.set_index('hour_utc')['liquidation_events'].resample(frequency).agg(['sum','size'])
    values=values.loc[values['size']>0].reset_index()
    values.columns=['Thời gian UTC','Số thanh lý','Giờ quan sát']
    return values


def decay_response(baseline,branching,half_life_minutes,burst,horizon_minutes=120):
    require(all(math.isfinite(float(x)) for x in (baseline,branching,half_life_minutes,burst,horizon_minutes)),'Non-finite Hawkes assumption')
    require(baseline>=0 and 0<=branching<1 and half_life_minutes>0 and burst>=0 and horizon_minutes>0,'Invalid Hawkes assumptions')
    beta=math.log(2)/(half_life_minutes/60)
    minutes=np.linspace(0,horizon_minutes,241)
    # Conditional first-generation kernel response to a simultaneous burst.
    # Does not simulate future events or subsequent generations.
    return pd.DataFrame({'Phút sau cụm sự kiện':minutes,
                         'Cường độ giả định (sự kiện/giờ)':baseline+burst*branching*beta*np.exp(-beta*minutes/60),
                         'Cường độ nền (sự kiện/giờ)':np.full_like(minutes,baseline)})


def audit_status(run=ROOT/'data/runs/recovery_20261020'):
    result=[]
    for name in ['audit_1_structure.json','audit_2_onchain.json','audit_3_research.json','freeze_manifest.json']:
        path=Path(run)/name
        if not path.exists():state='Chưa có'
        else:
            try:
                obj=read_json(path)
                state=('Đạt' if obj.get('all_integrity_passed') is True else 'Chưa đạt') if name!='freeze_manifest.json' else 'Đã tạo; cần đối chiếu hash'
            except (OSError,ValueError):state='Không đọc được'
        result.append({'Tệp kiểm định':name,'Trạng thái':state})
    return result
