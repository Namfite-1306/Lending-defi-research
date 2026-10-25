"""Incremental H1 analyses accept only reconciled full quarterly snapshots."""
import json
from collections import defaultdict
from pathlib import Path
import numpy as np
from defi_models.core import DEFAULTS,Portfolio
from defi_models.statistics import breakpoint
from .common import DATA,OUT,read,write,save,digest,now
from .h1 import summary


def run(folder=DATA/'h1',out=OUT/'h1'):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);all_curves=[];all_breaks=[];baselines=[];accepted=[]
    plan=Path(folder)/'quarter_plan.json'
    if not plan.exists():save(out/'summary.json',{'status':'pending_plan','full_snapshots':0,'required':15});return
    for scope in summary(folder):
        if not scope.get('full_snapshot_complete'):continue
        root=Path(folder)/scope['quarter'];dest=out/scope['quarter'];dest.mkdir(exist_ok=True)
        freeze=json.loads((root/'freeze_manifest.json').read_text())
        if not all(digest(root/name)==value for name,value in freeze['files'].items()):raise ValueError('Quarterly frozen snapshot hash changed')
        identity={'positions':digest(root/'positions.csv'),'validation':digest(root/'validation.csv'),'analysis_version':2}
        cached=dest/'source_identity.json'
        if cached.exists() and json.loads(cached.read_text())==identity:
            curves=read(dest/'stress_curves.csv');breaks=read(dest/'breakpoints.csv');baseline=read(dest/'baseline.csv')
        else:
            records=read(root/'positions.csv');checks=read(root/'validation.csv');p=Portfolio(records,DEFAULTS)
            if len(p.accounts)!=scope['active_debt_wallets'] or len(checks)!=len(p.accounts):raise ValueError('Full snapshot wallet coverage changed')
            hf,debt=p.stress();reported=np.array([float(r['hf_reported']) for r in sorted(checks,key=lambda r:r['account'])])
            if not np.all(np.abs(hf-reported)/np.maximum(abs(reported),1e-12)<=1e-4):raise ValueError('Independent model-HF gate failed')
            baseline=[dict(quarter=scope['quarter'],block=scope['block'],active_wallets=len(hf),debt_usd=float(debt.sum()),
              eligible_wallets=int((hf<1).sum()),eligible_debt_usd=float(debt[hf<1].sum()),
              debt_share_hf_below_1_05=float(debt[hf<1.05].sum()/debt.sum()),debt_share_hf_below_1_1=float(debt[hf<1.1].sum()/debt.sum()),debt_share_hf_below_1_2=float(debt[hf<1.2].sum()/debt.sum()))]
            curves=[];breaks=[]
            for mapping,cfg in [('factor_family_1to1',DEFAULTS),('direct_WETH_WBTC_only',dict(DEFAULTS,eth_symbols=['WETH'],btc_symbols=['WBTC']))]:
                p=Portfolio(records,cfg)
                for scenario,eth,btc in [('ETH_only',1,0),('BTC_only',0,1),('joint',1,1)]:
                    series=[]
                    for shock in np.linspace(0,.6,61):
                        hf,debt=p.stress(shock*eth,shock*btc);e=hf<1
                        row=dict(quarter=scope['quarter'],block=scope['block'],mapping=mapping,scenario=scenario,shock=float(shock),
                          eligible_wallets=int(e.sum()),eligible_debt_usd=float(debt[e].sum()),total_debt_usd=float(debt.sum()),eligible_debt_share=float(debt[e].sum()/debt.sum()))
                        curves.append(row);series.append(row)
                    for step in [1,2,5]:
                        subset=series[::step];x=[r['shock'] for r in subset];y=[r['eligible_debt_share'] for r in subset];fit=breakpoint(x,y)
                        delta=np.diff([r['eligible_debt_usd'] for r in subset]);j=int(delta.argmax())
                        breaks.append(dict(quarter=scope['quarter'],mapping=mapping,scenario=scenario,grid_step_percent=step,share_knot=fit.get('knot'),
                          largest_usd_jump_from=x[j],largest_usd_jump_to=x[j+1],largest_usd_jump=float(delta[j]),descriptive_only=True))
            write(dest/'stress_curves.csv',curves);write(dest/'breakpoints.csv',breaks);write(dest/'baseline.csv',baseline);save(cached,identity)
        accepted.append(scope['quarter']);all_curves+=curves;all_breaks+=breaks;baselines+=baseline
    write(out/'stress_curves.csv',all_curves);write(out/'breakpoints.csv',all_breaks);write(out/'baseline_by_quarter.csv',baselines)
    # Leave-one-quarter-out is a stability diagnostic, not a sampling CI for a census.
    loo=[]
    for scenario in ['ETH_only','BTC_only','joint']:
        rows=[r for r in all_curves if r['scenario']==scenario and r['mapping']=='factor_family_1to1'];by=defaultdict(list)
        for r in rows:by[r['quarter']].append(r)
        if len(by)<3:continue
        for omit in ['none']+sorted(by):
            groups=[sorted(rs,key=lambda r:float(r['shock'])) for q,rs in by.items() if q!=omit]
            x=np.array([float(r['shock']) for r in groups[0]]);y=np.mean([[float(r['eligible_debt_share']) for r in rs] for rs in groups],axis=0)
            fit=breakpoint(x,y);loo.append(dict(scenario=scenario,omitted_quarter=omit,quarters=len(groups),share_knot=fit.get('knot'),weighting='equal_quarter',descriptive_only=True))
    write(out/'leave_one_quarter_out.csv',loo)
    save(out/'summary.json',{'updated_utc':now(),'status':'completed_scoped' if len(accepted)==15 else 'partial_full_quarters_only',
      'required':15,'full_snapshots':len(accepted),'complete_quarters':accepted,'quarter_end_utc':True,
      'limitations':['Only reconciled full snapshots enter these tables','Incomplete/sample snapshots never count as full',
        'Static eligible risk debt, not realized liquidation volume','Direct-token-only case holds derivatives fixed; sensitivity assumption, not measured depeg',
        'Shock-grid rows are deterministic dependent outputs; no independent-observation p-values','Leave-one-quarter-out diagnoses stability, not census sampling uncertainty']})
    return accepted

if __name__=='__main__':run()
