"""NB controls on the same common bins and validation-selected feature group."""
import math,json
import numpy as np
from defi_models.core import stamp
from .h4 import history
from .h4_nb import fit,prediction,score,bootstrap
from .h4_extended import feature_groups
from .residual_v2 import bootstrap_segments
from .v2_common import *

def run(panel_filename='h4_panel_5min.npz',primary_subdir='h4',output_subdir='h4_nb'):
    primary=load(OUT/primary_subdir/'summary.json',{})
    if primary.get('status')!='completed_exploratory':raise ValueError('Primary feature selection not complete')
    panel=np.load(DATA/panel_filename);t=panel['t'];y=panel['y'];features=panel['X'];spec=primary['selected_spec_by_validation'];names=panel['names'].tolist()
    selected=load(OUT/primary_subdir/'fitted_models.json')[spec+'_hawkes'];raw=panel['old'] if spec=='baseline_hourly' else features[:,feature_groups(names)[spec]]
    X=np.column_stack([np.ones(len(y)),np.nan_to_num((raw-np.array(selected['center']))/np.array(selected['scale']))]);dt=1/12
    common=panel['old_valid']&np.isfinite(features).all(axis=1);train=(t<stamp('2025-01-01T00:00:00Z'))&common&(t>=t[0]+60*3600)
    panel.close()
    val=(t>=stamp('2025-01-01T00:00:00Z'))&(t<stamp('2025-07-01T00:00:00Z'))&common;test=(t>=stamp('2025-07-01T00:00:00Z'))&common
    out=OUT/output_subdir;out.mkdir(parents=True,exist_ok=True);rows=[];candidates=[];diagnostics={};models={}
    for excitation in [False,True]:
        name='extended_nb_hawkes' if excitation else 'extended_nb_no_excitation';best=None
        for half in [.25,.5,2.,6.] if excitation else [1.]:
            g=history(y,half,dt) if excitation else np.zeros(len(y))
            try:
                p=fit(X,y,g,train,dt,excitation);mu,r=prediction(X,g,p,dt,excitation);value=float(score(y[val],mu[val],r).sum())
                candidates.append({'model':name,'half_life_hours':half,'validation_loglik':value,'status':'converged'})
                if best is None or value>best[0]:best=(value,half,p)
            except ValueError as exc:candidates.append({'model':name,'half_life_hours':half,'status':'failed','error':str(exc)})
        if best is None:raise ValueError('No NB fit for '+name)
        _,half,initial=best;g=history(y,half,dt) if excitation else np.zeros(len(y));p=fit(X,y,g,train|val,dt,excitation,initial);mu,r=prediction(X,g,p,dt,excitation)
        eta=float(p[X.shape[1]]) if excitation else 0.;base=np.exp(X@p[:X.shape[1]])*dt
        idx=np.flatnonzero(test);segments=np.split(idx,np.where(np.diff(idx)>1)[0]+1);segment=max(segments,key=len)
        diagnostic=bootstrap_segments(y,base,g,idx,eta,half,dt,dispersion=r);diagnostics[name]=diagnostic
        rows.append({'model':name,'spec':spec,'test_bins':int(test.sum()),'test_events':int(y[test].sum()),'test_loglik':float(score(y[test],mu[test],r).sum()),
          'test_count_MAE':float(np.mean(abs(y[test]-mu[test]))),'expected_test_events':float(mu[test].sum()),'eta':eta,'dispersion_r':r,'half_life_hours':half if excitation else None})
        models[name]=p.tolist();write(out/'model_comparison.csv',rows);write(out/'candidates.csv',candidates);save(out/'residuals.json',diagnostics);print('EXTENDED NB',rows[-1],flush=True)
    result={'status':'completed_exploratory','updated_utc':now(),'selected_spec':spec,'models':models,'panel_sha256':digest(DATA/panel_filename),
      'scope':primary.get('scope',{}),'scope_type':primary.get('scope_type','full_target'),'target_period_complete':primary.get('target_period_complete',True),
      'limitations':['Posthoc distribution and feature upgrade; prior test already examined','Same common test bins as Poisson ablations','Residual bootstrap fixes parameters and market path; not structural causality']}
    save(out/'summary.json',result);return result
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--with-utilization',action='store_true');a=p.parse_args()
    if a.with_utilization:r=run(panel_filename='h4_util_panel_5min.npz',primary_subdir='h4_util',output_subdir='h4_util_nb')
    else:r=run()
    print(json.dumps(r,ensure_ascii=False))
