"""Score frozen earlier fits on the exact revised primary test support."""
import numpy as np,math
from .next_common import *
from .h4 import history,logscore
from .h4_nb import score as nb_score
from .h4_extended import feature_groups
from .repair_h3 import predict as repair_predict,DT,LONG_HALF
from .hurdle_model import predictions as hurdle_predictions,score as hurdle_score
from defi_models.core import stamp

def run():
    with np.load(DATA/'h4_prefix_panel_5min.npz') as a:
        keep=a['t']<PRIMARY_END;t=a['t'][keep];y=a['y'][keep];f=a['X'][keep];names=a['names'].tolist();common=a['old_valid'][keep]&np.isfinite(f).all(axis=1)
    te=(t>=stamp('2025-07-01T00:00:00Z'))&common;raw=f[:,feature_groups(names)['oracle_gas']];rows=[]
    def record(name,ll,mean,p):
        rows.append({'model':name,'test_bins':int(te.sum()),'test_events':int(y[te].sum()),'test_loglik':float(ll[te].sum()),'expected_test_events':float(mean[te].sum()),
          'expected_observed_ratio':float(mean[te].sum()/y[te].sum()),'test_MAE':float(abs(mean[te]-y[te]).mean()),'event_Brier':float(((p[te]-(y[te]>0))**2).mean())})
    old=load(V2_OUT/'h4_prefix/fitted_models.json')['oracle_gas_hawkes'];X=np.c_[np.ones(len(y)),np.nan_to_num((raw-np.array(old['center']))/np.array(old['scale']))]
    nb=load(V2_OUT/'h4_prefix_nb/summary.json')['models'];p=np.array(nb['extended_nb_hawkes']);k=X.shape[1];mean=np.exp(X@p[:k])*DT+p[k]*history(y,.5,DT);r=math.exp(p[-1])
    record('earlier_exp_NB_hawkes',nb_score(y,mean,r),mean,1-np.exp(-r*np.log1p(mean/r)))
    repair=load(REPAIR_OUT/'h3/fitted_models.json')
    for name in ['softplus_nb_hawkes','softplus_adaptive_poisson_hawkes']:
        m=repair[name];a=np.c_[raw,np.log1p(history(y,LONG_HALF,DT))] if m['architecture']=='softplus_adaptive' else raw
        X=np.c_[np.ones(len(y)),np.nan_to_num((a-np.array(m['center']))/np.array(m['scale']))];g=history(y,m['half'],DT);mean,r=repair_predict(X,g,np.array(m['parameters']),m['kind'],m['family'],m['excitation'])
        ll=nb_score(y,mean,r) if r is not None else logscore(y,mean);prob=1-np.exp(-r*np.log1p(mean/r)) if r is not None else -np.expm1(-mean)
        record('earlier_repair_'+name,ll,mean,prob)
    with np.load(DATA_NEXT/'activity_panel.npz') as a:flows=a['X'];past=a['history']
    controls={'constant':np.empty((len(y),0)),'market':raw,'activity':np.c_[raw,flows],'activity_history':np.c_[raw,flows,past]}
    for name,m in load(OUT/'h3/fitted_models.json').items():
        X=np.c_[np.ones(len(y)),np.nan_to_num((controls[name]-np.array(m['center']))/np.array(m['scale']))]
        pr=hurdle_predictions(X,(np.array(m['event_parameters']),np.array(m['size_parameters'])));record('hurdle_'+name,hurdle_score(y,pr),pr[-1],pr[1])
        if name==load(OUT/'h3/summary.json')['selected_by_validation']:
            calibration=[]
            for lower,upper in [(0,.01),(.01,.05),(.05,.1),(.1,.2),(.2,.5),(.5,1.0000001)]:
                mask=te&(pr[1]>=lower)&(pr[1]<upper)
                calibration.append({'probability_lower':lower,'probability_upper':upper,'bins':int(mask.sum()),'mean_forecast_probability':float(pr[1][mask].mean()) if mask.any() else None,
                  'observed_event_frequency':float((y[mask]>0).mean()) if mask.any() else None,'expected_count':float(pr[-1][mask].sum()),'observed_count':int(y[mask].sum())})
            write(OUT/'h3/event_calibration.csv',calibration)
    write(OUT/'h3/common_primary_comparison.csv',rows)
    save(OUT/'h3/common_primary_comparison_scope.json',{'primary_end_exclusive':PRIMARY_END_UTC,'same_test_support':len({(r['test_bins'],r['test_events']) for r in rows})==1,
      'interpretation':'Descriptive rescoring of frozen fits; earlier training protocols/availability assumptions differ. No test-based reselection and no causal attribution of gain.'})
    return rows

if __name__=='__main__':run()
