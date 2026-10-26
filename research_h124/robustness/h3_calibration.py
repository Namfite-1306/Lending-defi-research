"""Train-only hurdle fits and validation-only recalibration.

No refit after calibration. Earlier test remains an exploratory comparison.
Future independent holdout is explicitly pending, not invented from old test.
"""
import argparse,math
import numpy as np
from scipy.optimize import minimize
from scipy.special import expit
from research_h124.hurdle_model import fit,predictions,score,diagnostics
from research_h124.h4_nb import score as nb_score
from research_h124.h4_extended import feature_groups
from research_h124.repair_h3 import masks
from research_h124.next_common import DATA,DATA_NEXT,PRIMARY_END as END_TIMESTAMP
from .common import *

def calibrated(pred,cal):
    z,prob,mu,r,p0,den,mean=pred
    a,b,delta,log_r=cal
    z=a+b*z;prob=expit(z)
    underlying=mu+np.log(-np.expm1(-mu))
    mu=np.logaddexp(0,underlying+delta)+1e-9;r=math.exp(log_r)
    log_p0=-r*np.log1p(mu/r);p0=np.exp(log_p0);den=-np.expm1(log_p0)
    return z,prob,mu,r,p0,den,prob*mu/den

def fit_calibration(y,pred):
    raw=np.asarray(pred[0]);positive=y>0;truth=positive.astype(float)
    def event_objective(p):
        z=p[0]+p[1]*raw
        return float((np.logaddexp(0,z)-truth*z).mean()+1e-4*(p[0]**2+(p[1]-1)**2))
    probability=minimize(event_objective,[0,1],method='L-BFGS-B',bounds=[(-10,10),(.1,3)])
    if not probability.success:raise ValueError('Probability recalibration did not converge')
    a,b=probability.x;r=pred[3];base_log_r=math.log(r)
    mu=pred[2][positive];underlying=mu+np.log(-np.expm1(-mu));v=y[positive]
    def size_objective(p):
        mean=np.logaddexp(0,underlying+p[0])+1e-9;dispersion=math.exp(p[1]);log_p0=-dispersion*np.log1p(mean/dispersion)
        ll=nb_score(v,mean,dispersion)-np.log(-np.expm1(log_p0))
        return float(-ll.mean()+1e-4*(p[0]**2+(p[1]-base_log_r)**2))
    size=minimize(size_objective,[0,base_log_r],method='L-BFGS-B',bounds=[(-10,10),(-8,8)])
    if not size.success:raise ValueError('Positive-size recalibration did not converge')
    return {'none':[0.,1.,0.,base_log_r],'probability_only':[float(a),float(b),0.,base_log_r],
            'two_part':[float(a),float(b),float(size.x[0]),float(size.x[1])]}

def run(reps=499):
    folder=OUT/'h3';fitted_path=OLD/'h3/fitted_models.json';frozen=load(fitted_path)
    paths=[DATA/'h4_prefix_panel_5min.npz',DATA_NEXT/'activity_panel.npz',fitted_path]
    source_hashes={str(p.relative_to(ROOT)):digest(p) for p in paths}
    protocol={'locked_utc':now(),'train_end_exclusive':'2025-01-01T00:00:00Z','validation_start':'2025-01-01T00:00:00Z','validation_end_exclusive':'2025-07-01T00:00:00Z',
      'test_end_exclusive':PRIMARY_END,'models':['activity','activity_history'],'calibrations':['none','probability_only','two_part'],
      'selection':'validation log-score with 0.5–2 count ratio screen; never select by test PIT','refit_after_calibration':False,'warmup_days':7,
      'test_previously_seen':True,'independent_holdout':'pending prospective collection after model lock; excluded quarters are not restored','source_hashes':source_hashes,'seed':42,'pit_null_replications':reps}
    # Written before fitting or test scoring. A passing old-test diagnostic will
    # still not be relabelled a prospective independent validation.
    save(folder/'protocol.json',protocol)
    with np.load(paths[0]) as a:
        keep=a['t']<END_TIMESTAMP;t=a['t'][keep];y=a['y'][keep];features=a['X'][keep];names=a['names'].tolist();common=a['old_valid'][keep]&np.isfinite(features).all(axis=1)
    with np.load(paths[1]) as a:
        if not np.array_equal(t,a['t']) or not np.array_equal(y,a['y']):raise ValueError('Activity/target clock mismatch')
        flows=a['X'];history=a['history']
    tr,val,test=masks(t,common);tr &= t>=t[0]+7*86400
    market=features[:,feature_groups(names)['oracle_gas']]
    raw={'activity':np.c_[market,flows],'activity_history':np.c_[market,flows,history]}
    rows=[];parameters={};chosen=[];test_predictions={};all_predictions={};errors=[]
    save(folder/'errors.json',[])
    for name in protocol['models']:
        try:
            model=frozen[name];center=np.asarray(model['center']);scale=np.asarray(model['scale'])
            if not np.isfinite(raw[name][tr|val|test]).all():raise ValueError('Missing model input on included bins')
            X=np.c_[np.ones(len(y)),np.nan_to_num((raw[name]-center)/scale)]
            params=fit(X,y,tr,float(model['ridge']))
            base=predictions(X,params);validation=tuple(v[val] if isinstance(v,np.ndarray) else v for v in base)
            calibrators=fit_calibration(y[val],validation)
            candidates=[]
            for variant,cal in calibrators.items():
                pr=calibrated(validation,cal);ratio=float(pr[-1].sum()/y[val].sum());ll=float(score(y[val],pr).sum())
                candidates.append({'model':name,'calibration':variant,'validation_loglik':ll,'validation_count_ratio':ratio,'validation_eligible':.5<=ratio<=2,'parameters':cal})
            accepted=[r for r in candidates if r['validation_eligible']]
            best=max(accepted,key=lambda r:r['validation_loglik']) if accepted else None
            parameters[name]={'event_parameters':params[0].tolist(),'size_parameters':params[1].tolist(),'ridge':model['ridge'],'calibration_candidates':candidates,'selected_calibration':best['calibration'] if best else None,'center':center.tolist(),'scale':scale.tolist()}
            save(folder/'parameters.json',parameters)
            for r in candidates:
                pr=calibrated(base,r['parameters']);pt=tuple(v[test] if isinstance(v,np.ndarray) else v for v in pr)
                row={k:v for k,v in r.items() if k!='parameters'}
                row.update(selected_within_model=best is not None and r['calibration']==best['calibration'],test_bins=int(test.sum()),test_events=int(y[test].sum()),
                  test_loglik=float(score(y[test],pt).sum()),expected_observed_ratio=float(pt[-1].sum()/y[test].sum()),event_Brier=float(((pt[1]-(y[test]>0))**2).mean()),all_bin_MAE=float(abs(pt[-1]-y[test]).mean()),conditional_positive_MAE=float(abs((pt[2]/pt[5])[y[test]>0]-y[test][y[test]>0]).mean()))
                rows.append(row)
                all_predictions[name+'|'+r['calibration']]=pr
                if row['selected_within_model']:
                    chosen.append(row);test_predictions[name]=pr
            write(folder/'comparison.csv',rows);print('H3 VALIDATION CALIBRATION',name,best['calibration'] if best else 'no eligible fit',flush=True)
        except Exception as exc:errors.append({'model':name,'error':str(exc)[:220]});save(folder/'errors.json',errors)
    selected=max(chosen,key=lambda r:r['validation_loglik']) if chosen else None
    residuals={};all_residuals={}
    for row in rows:
        name=row['model'];key=name+'|'+row['calibration'];d=diagnostics(y,all_predictions[key],np.flatnonzero(test),reps);all_residuals[key]=d
        row['PIT_KS_p']=d['uniform_null_KS_p'];row['PIT_ACF_p']=d['uniform_null_ACF_p']
        if row['selected_within_model']:residuals[name]=d
        print('H3 CALIBRATION PIT',key,d['uniform_null_KS_p'],d['uniform_null_ACF_p'],flush=True)
        save(folder/'residuals.json',residuals)
        save(folder/'all_residuals.json',all_residuals)
        write(folder/'comparison.csv',rows)
    if any(digest(ROOT/p)!=h for p,h in source_hashes.items()):raise ValueError('Frozen source changed')
    result={'updated_utc':now(),'status':'completed_exploratory' if selected else 'no_eligible_model','selection':selected,'models_scored':len(rows),'residuals':residuals,'errors':errors,'deployment_ready':False,
      'independent_holdout_available':False,'fit_training':'train only; recalibration on validation only; no train+validation refit',
      'limitations':['Old test already seen; cannot manufacture an independent holdout','PIT tests condition on fitted model; no parameter uncertainty','Any gain is from an exploratory validation-selected calibration, not a causal or prospective claim','Original production/research fits are retained unchanged']}
    save(folder/'errors.json',errors);save(folder/'summary.json',result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--replications',type=int,default=499);a=p.parse_args();run(a.replications)
