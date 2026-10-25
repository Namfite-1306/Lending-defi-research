"""RQ3: temporal/verified recursive leverage, matching and seven-day outcomes.

Shared production implementation. Run: python -m defi_models.rq3 --help
"""
import sys
from pathlib import Path
if __package__ in (None, ''):
    # Place this file anywhere inside the repository; locate shared audited code.
    _root = next((p for p in Path(__file__).resolve().parents if (p/'defi_models/core.py').is_file()), None)
    if _root is None:
        raise SystemExit('Place this file inside Lending-defi-research, which must contain defi_models/. See HUONG_DAN_CHAY.md.')
    sys.path.insert(0, str(_root))
    __package__ = 'defi_models'
import json, math
from collections import Counter
import numpy as np
from scipy.spatial import cKDTree
from .core import rows, write_csv, stamp, iso, require, summary
from .statistics import glm

def temporal_positive(record,window,cutoff):
    available=stamp(record['label_available_at']);borrow=float(record['borrow_stamp'])
    require(math.isfinite(borrow) and available>=borrow,'Recursive label precedes its borrow')
    return int(record['window_hours'])==window and available<=cutoff

def rq3(data,out,cfg):
    p,scope=data.snapshot();cutoff=data.snapshot_time(scope['block']);window=cfg['recursive_window_hours']
    positive=set();evidence=Counter();mode=cfg['recursive_label']
    if mode=='temporal':
        for r in rows(data.path('recursive_candidates_full_history.csv')):
            if temporal_positive(r,window,cutoff):
                # Future whole-window right censoring is irrelevant once positive evidence is observed.
                positive.add(r['account']);evidence[r['account']]+=1
    else:
        for r in data.read('recursive_receipt_verification.csv'):
            if r['status'].startswith('verified') and int(r['block'])<=scope['block']:positive.add(r['account']);evidence[r['account']]+=1
    accounts=p.accounts;treated=np.array([a in positive for a in accounts]);hf,debt=p.stress();stressed,_=p.stress(.2,.2)
    require(np.any(treated) and np.any(~treated),'No treated/control overlap at snapshot; change label mode or snapshot')
    denom=p.c.sum(axis=1);eth_share=np.divide(p.c[:,p.eth].sum(axis=1),denom,out=np.zeros_like(denom),where=denom>0)
    btc_share=np.divide(p.c[:,p.btc].sum(axis=1),denom,out=np.zeros_like(denom),where=denom>0)
    feature=np.column_stack([np.log1p(debt),np.minimum(hf,10),eth_share,btc_share]);sd=feature.std(axis=0);sd[sd==0]=1
    Z=(feature-feature.mean(axis=0))/sd
    ti=np.flatnonzero(treated);ci=np.flatnonzero(~treated);tree=cKDTree(Z[ci]);k=min(30,len(ci))
    distances,neighbors=tree.query(Z[ti],k=k)
    if k==1:distances=distances[:,None];neighbors=neighbors[:,None]
    # Deterministic greedy matching without replacement, lowest-distance treated first.
    used=set();pairs=[]
    for pos in np.argsort(distances[:,0],kind='stable'):
        for distance,neighbor in zip(distances[pos],neighbors[pos]):
            control=int(ci[int(neighbor)])
            if distance>cfg['match_caliper']:break
            if control not in used:used.add(control);pairs.append((int(ti[pos]),control,float(distance)));break
    require(len(pairs)>=2,'Fewer than two matched pairs; inspect overlap/caliper, do not claim effect')
    future=Counter();horizon=cutoff+cfg['outcome_days']*86400
    bounds=json.loads((data.run/'block_range.json').read_text(encoding='utf8'))
    require(horizon<=stamp(bounds['end_exclusive_utc']),'Outcome horizon is right-censored by data end')
    for r in data.read('liquidations_model_table.csv'):
        if r['protocol']=='aave_v3' and scope['block']<int(r['block']) and stamp(r['timestamp_utc'])<=horizon:future[r['borrower']]+=1
    y=np.array([future[a]>0 for a in accounts],int);result=[]
    for pair,(i,j,distance) in enumerate(pairs,1):
        result.append(dict(pair=pair,treated=accounts[i],control=accounts[j],distance=distance,treated_hf=hf[i],control_hf=hf[j],
            treated_liquidated=int(y[i]),control_liquidated=int(y[j]),treated_stress_eligible=int(stressed[i]<1),control_stress_eligible=int(stressed[j]<1)))
    write_csv(out/'matched_pairs.csv',result)
    balance=[];ii=np.array([i for i,j,d in pairs]);jj=np.array([j for i,j,d in pairs])
    for k,name in enumerate(['log1p_debt','HF_capped_10','ETH_collateral_share','BTC_collateral_share']):
        denom=math.sqrt((feature[ii,k].var()+feature[jj,k].var())/2)
        balance.append(dict(feature=name,treated_mean=feature[ii,k].mean(),control_mean=feature[jj,k].mean(),standardized_mean_difference=(feature[ii,k].mean()-feature[jj,k].mean())/denom if denom>0 else None))
    write_csv(out/'matching_balance.csv',balance)
    diff=y[ii]-y[jj];rng=np.random.default_rng(cfg['seed']);boot=[rng.choice(diff,len(diff),replace=True).mean() for _ in range(cfg['bootstrap_repetitions'])]
    indices=np.ravel(np.column_stack([ii,jj]));X=np.column_stack([np.ones(len(indices)),treated[indices].astype(float),Z[indices]])
    regression={'status':'not_identified_no_outcome_variation'}
    if len(np.unique(y[indices]))==2:
        fit,mu=glm(X,y[indices],family='logistic',ridge=1e-3)
        regression=dict(status='penalized_association_only' if fit.success else 'fit_failed_do_not_interpret',converged=bool(fit.success),message=str(fit.message),coefficients=fit.x.tolist(),coefficient_names=['intercept','treated','log1p_debt_z','HF_z','ETH_share_z','BTC_share_z'],ridge=.001)
    return summary('exploratory','Matched observational comparison using labels available before snapshot',
      ['No-observed-motif controls are not proven unlevered','Temporal labels are candidates; verified positives are a small selected sample',
       'Conditional associations and paired bootstrap are not causal identification; no population extrapolation',
       'Bootstrap holds matching fixed; balance and unmatched treated must be reviewed'],
       label_mode=mode,cutoff_utc=iso(cutoff),outcome_end_utc=iso(horizon),treated_in_snapshot=int(treated.sum()),matched_pairs=len(pairs),
       unmatched_treated=int(treated.sum())-len(pairs),liquidation_risk_difference=diff.mean(),paired_bootstrap_95=np.quantile(boot,[.025,.975]),
       stress_eligibility_difference=np.mean((stressed[ii]<1).astype(int)-(stressed[jj]<1).astype(int)),regression=regression)

def main(argv=None):
    from . import __main__ as _runner
    _runner.MODELS.update({3: rq3})
    from .member_cli import run_member
    return run_member([3], argv)


if __name__ == "__main__":
    raise SystemExit(main())
