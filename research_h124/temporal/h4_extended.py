"""Exploratory sequential ablations; all models share exactly the same bins."""
import json,math,argparse
import numpy as np
from .h4 import history,fit,predict,logscore,bootstrap_residual
from .residual_v2 import bootstrap_segments
from defi_models.core import stamp,iso
from .v2_common import *

def feature_groups(names):
    oracle=[i for i,n in enumerate(names) if n.startswith(('ETH_','BTC_','hour_'))]
    gas=[i for i,n in enumerate(names) if n.startswith('sampled_')]
    regime=[i for i,n in enumerate(names) if n.startswith('pool_revision_')]
    stable=[i for i,n in enumerate(names) if n.startswith(('USDC_','USDT_','DAI_'))]
    result={'oracle':oracle,'oracle_gas':oracle+gas,'oracle_gas_regime':oracle+gas+regime,'oracle_gas_regime_stable':oracle+gas+regime+stable}
    usage=[i for i,n in enumerate(names) if n.startswith('reserve_')]
    if usage:result['oracle_gas_regime_stable_utilization']=oracle+gas+regime+stable+usage
    return result

def run(repetitions=49,panel_filename='h4_panel_5min.npz',readiness_filename='h4_data_readiness.json',output_subdir='h4'):
    readiness=load(OUT/readiness_filename,{})
    if readiness.get('status')!='completed_scoped':raise ValueError('H4 data audit not complete')
    panel_path=DATA/panel_filename
    if digest(panel_path)!=readiness['panel_sha256']:raise ValueError('H4 panel hash mismatch')
    panel=np.load(panel_path);t=panel['t'];y=panel['y'];features=panel['X'];old=panel['old'];names=panel['names'].tolist();dt=1/12
    common=panel['old_valid']&np.isfinite(features).all(axis=1)
    panel.close()
    train=(t<stamp('2025-01-01T00:00:00Z'))&common&(t>=t[0]+60*3600)
    val=(t>=stamp('2025-01-01T00:00:00Z'))&(t<stamp('2025-07-01T00:00:00Z'))&common
    test=(t>=stamp('2025-07-01T00:00:00Z'))&common
    if min(train.sum(),val.sum(),test.sum())<1000:raise ValueError('Insufficient common chronological sample')
    out=OUT/output_subdir;out.mkdir(parents=True,exist_ok=True);groups={'baseline_hourly':None,**feature_groups(names)}
    fitted={};matrices={};scores=[];candidates=[];g_history={h:history(y,h,dt) for h in [.25,.5,2.,6.]};zero=np.zeros(len(y))
    for spec,indices in groups.items():
        raw=old if indices is None else features[:,indices];labels=['abs_ETH_1h','down_ETH_1h','abs_BTC_1h','down_BTC_1h','ETH_rv24h','BTC_rv24h','hour_sin','hour_cos'] if indices is None else [names[j] for j in indices]
        center=raw[train].mean(axis=0);scale=raw[train].std(axis=0);scale[scale==0]=1
        X=np.column_stack([np.ones(len(y)),np.nan_to_num((raw-center)/scale)]);matrices[spec]=X
        for excitation in [False,True]:
            model=spec+('_hawkes' if excitation else '_poisson');best=None
            for half in [.25,.5,2.,6.] if excitation else [1.]:
                g=g_history[half] if excitation else zero
                try:
                    par,opt=fit(X,y,g,train,dt,excitation);mu,_=predict(X,g,par,dt,excitation);value=float(logscore(y[val],mu[val]).sum())
                    candidates.append({'model':model,'half_life_hours':half,'validation_loglik':value,'status':'converged'})
                    if best is None or value>best[0]:best=(value,half,par)
                except ValueError as exc:candidates.append({'model':model,'half_life_hours':half,'status':'failed','error':str(exc)})
            if best is None:raise ValueError('No converged candidate: '+model)
            value,half,initial=best;g=g_history[half] if excitation else zero
            par,opt=fit(X,y,g,train|val,dt,excitation,initial);mu,base=predict(X,g,par,dt,excitation);ll=logscore(y,mu)
            row={'model':model,'spec':spec,'excitation':excitation,'validation_loglik':value,'test_bins':int(test.sum()),'test_events':int(y[test].sum()),
              'test_loglik':float(ll[test].sum()),'test_count_MAE':float(np.mean(abs(y[test]-mu[test]))),'expected_test_events':float(mu[test].sum()),
              'event_Brier':float(np.mean(((1-np.exp(-mu[test]))-(y[test]>0))**2)),'eta':float(par[-1]) if excitation else 0.,'half_life_hours':half if excitation else None}
            scores.append(row);fitted[model]={'spec':spec,'excitation':excitation,'half':half,'par':par,'mu':mu,'base':base,'g':g,'ll':ll,
              'labels':labels,'center':center,'scale':scale,'train_constant_features':[labels[j] for j in range(len(labels)) if np.ptp(raw[train,j])==0],
              'pretest_constant_features':[labels[j] for j in range(len(labels)) if np.ptp(raw[train|val,j])==0]}
            write(out/'model_comparison.csv',scores);write(out/'candidates.csv',candidates);print('EXTENDED H4',model,row['test_loglik'],flush=True)
    selected=max((r for r in scores if r['excitation']),key=lambda r:r['validation_loglik'])['spec']
    diagnostics={};rolling=[]
    tested=[f'baseline_hourly_{family}' for family in ['poisson','hawkes']]+[f'{selected}_{family}' for family in ['poisson','hawkes']]
    for model in dict.fromkeys(tested):
        f=fitted[model];indices=np.flatnonzero(test);segments=np.split(indices,np.where(np.diff(indices)>1)[0]+1);segment=max(segments,key=len)
        diag=bootstrap_segments(y,f['base'],f['g'],indices,float(f['par'][-1]) if f['excitation'] else 0.,f['half'],dt,repetitions)
        diag.update(start=iso(t[indices[0]]),end_exclusive=iso(t[indices[-1]]+300))
        diagnostics[model]=diag;save(out/'residuals.json',diagnostics)
        for lo,hi in [('2025-07-01','2025-10-01'),('2025-10-01','2026-01-01'),('2026-01-01','2026-04-01'),('2026-04-01','2026-07-01'),('2026-07-01','2026-10-01')]:
            lower=stamp(lo+'T00:00:00Z');upper=stamp(hi+'T00:00:00Z');tr=(t<lower)&common&(t>=t[0]+60*3600);te=(t>=lower)&(t<upper)&common
            p,_=fit(matrices[f['spec']],y,f['g'],tr,dt,f['excitation'],f['par']);prediction,_=predict(matrices[f['spec']],f['g'],p,dt,f['excitation'])
            rolling.append({'model':model,'start':lo,'end_exclusive':hi,'bins':int(te.sum()),'events':int(y[te].sum()),'loglik':float(logscore(y[te],prediction[te]).sum())})
    write(out/'rolling_quarter_scores.csv',rolling)
    estimates={name:{k:(v.tolist() if isinstance(v,np.ndarray) else v) for k,v in f.items() if k in ['spec','excitation','half','par','labels','center','scale','train_constant_features','pretest_constant_features']} for name,f in fitted.items()}
    save(out/'fitted_models.json',estimates)
    delta=fitted[selected+'_hawkes']['ll'][test]-fitted[selected+'_poisson']['ll'][test];days=t[test]//86400
    sums=np.array([delta[days==day].sum() for day in np.unique(days)]);rng=np.random.default_rng(42);boot=sums[rng.integers(0,len(sums),(500,len(sums)))].sum(axis=1)
    write(out/'heldout_predictions.csv',[{'bin_start_utc':iso(t[i]),'observed':int(y[i]),**{model:float(fitted[model]['mu'][i]) for model in dict.fromkeys(tested)}} for i in np.flatnonzero(test)])
    summary={'status':'completed_exploratory','updated_utc':now(),'selected_spec_by_validation':selected,'panel_sha256':digest(panel_path),
      'scope':readiness.get('source',{}),'scope_type':readiness.get('scope_type','full_target'),'target_period_complete':readiness.get('target_period_complete',True),
      'common_bins':int(common.sum()),'common_bin_coverage':float(common.mean()),'train_bins':int(train.sum()),'validation_bins':int(val.sum()),'test_bins':int(test.sum()),
      'test_events':int(y[test].sum()),'excitation_logscore_gain':float(delta.sum()),'daily_resampling_95_interval':np.quantile(boot,[.025,.975]).tolist(),
      'limitations':['Same chronological test as prior research: exploratory feature upgrade, not a new untouched confirmatory holdout',
        'All ten models use identical common bins; inspect excluded-bin coverage','Future-only revision dummies have no identified coefficient; see constant features',
        'Residual bootstrap conditions separately on all valid segments; ACF never bridges missing-bin gaps; fixed parameters/market path',
        'Oracle-implied returns and sampled gas, not continuous exchange prices or 5-minute gas medians','Conditional predictive excitation, not structural causality']}
    save(out/'summary.json',summary);print(json.dumps(summary,ensure_ascii=False),flush=True);return summary
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bootstrap',type=int,default=49);p.add_argument('--with-utilization',action='store_true');a=p.parse_args()
    if a.with_utilization:run(a.bootstrap,panel_filename='h4_util_panel_5min.npz',readiness_filename='h4_util_data_readiness.json',output_subdir='h4_util')
    else:run(a.bootstrap)
