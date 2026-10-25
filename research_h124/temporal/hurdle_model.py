"""Two-part event probability / positive-count model, selected on validation."""
import math,argparse
import numpy as np
from scipy.optimize import minimize
from scipy.special import expit,digamma,betainc
from .next_common import *
from .repair_h3 import masks
from .h4_nb import score as nb_score
from .h4 import ks_uniform
from .residual_v2 import segmented_acf
from .h4_extended import feature_groups
from defi_models.core import iso

def nb_positive(par,X,y,ridge):
    k=X.shape[1];z=X@par[:k];mu=np.logaddexp(0,z)+1e-9;r=math.exp(par[-1]);logp0=-r*np.log1p(mu/r);p0=np.exp(logp0);den=-np.expm1(logp0)
    ll=nb_score(y,mu,r)-np.log(den);d=r*(mu-y)/(mu*(r+mu))+p0*r/((r+mu)*den)
    grad=X.T@(d*expit(z))/len(y)
    dlogp0=-np.log1p(mu/r)+mu/(r+mu)
    dr=-(digamma(y+r)-digamma(r)+math.log(r)+1-np.log(r+mu)-(r+y)/(r+mu))-p0/den*dlogp0
    grad=np.r_[grad,float(dr.mean()*r)];penalty=par[:k].copy();penalty[0]=0;grad[:k]+=ridge*penalty
    return float(-ll.mean()+ridge*(penalty@penalty)/2),grad

def logistic(par,X,y,ridge):
    z=X@par;p=expit(z);penalty=par.copy();penalty[0]=0
    return float((np.logaddexp(0,z)-y*z).mean()+ridge*(penalty@penalty)/2),X.T@(p-y)/len(y)+ridge*penalty

def fit(X,y,mask,ridge):
    A=X[mask];v=y[mask];k=X.shape[1];q=np.zeros(k);prob=np.clip((v>0).mean(),1e-6,1-1e-6);q[0]=math.log(prob/(1-prob))
    event=minimize(lambda p:logistic(p,A,(v>0).astype(float),ridge),q,jac=True,method='L-BFGS-B',bounds=[(-20,20)]*k,options={'maxiter':700,'ftol':1e-11,'gtol':1e-7})
    pos=v>0;b=np.zeros(k+1);m=max(float(v[pos].mean())-1,.1);b[0]=m if m>20 else math.log(math.expm1(m));b[-1]=-1
    size=minimize(lambda p:nb_positive(p,A[pos],v[pos],ridge),b,jac=True,method='L-BFGS-B',bounds=[(-20,20)]*k+[(-8,8)],options={'maxiter':700,'ftol':1e-11,'gtol':1e-7})
    if not event.success or not size.success:raise ValueError('Hurdle fit failed: '+str(event.message)+'; '+str(size.message))
    return event.x,size.x

def predictions(X,params):
    event,size=params;z=X@event;prob=expit(z);mu=np.logaddexp(0,X@size[:-1])+1e-9;r=math.exp(size[-1]);p0=np.exp(-r*np.log1p(mu/r));den=-np.expm1(-r*np.log1p(mu/r));mean=prob*mu/den
    return z,prob,mu,r,p0,den,mean

def score(y,pred):
    z,prob,mu,r,p0,den,mean=pred;positive=y>0
    value=-np.logaddexp(0,z)
    value[positive]=-np.logaddexp(0,-z[positive])+nb_score(y[positive],mu[positive],r)-np.log(den[positive]);return value

def randomized_pit(y,pred,seed=42):
    z,q,mu,r,p0,den,mean=pred;p=r/(r+mu);positive=y>0
    upper=1-q;lower=np.zeros(len(y));upper[positive]=1-q[positive]+q[positive]*(betainc(r,y[positive]+1,p[positive])-p0[positive])/den[positive]
    lower[positive]=1-q[positive]+q[positive]*(betainc(r,y[positive],p[positive])-p0[positive])/den[positive]
    rng=np.random.default_rng(seed);u=lower+rng.random(len(y))*np.maximum(upper-lower,0);return np.clip(u,1e-12,1-1e-12)

def diagnostics(y,pred,indices,reps=499):
    sub=tuple(v[indices] if isinstance(v,np.ndarray) else v for v in pred);u=randomized_pit(y[indices],sub);lengths=[len(s) for s in np.split(indices,np.where(np.diff(indices)>1)[0]+1)]
    ks=ks_uniform(u);acf=segmented_acf(u,lengths);rng=np.random.default_rng(43);ks_sim=[];acf_sim=[]
    for _ in range(reps):
        values=rng.uniform(1e-12,1-1e-12,len(u));ks_sim.append(ks_uniform(values));acf_sim.append(segmented_acf(values,lengths))
    return {'reference':'Monte Carlo iid-uniform PIT null; fixed training fit, not parametric event bootstrap','replications':reps,'bins':len(u),'segments':len(lengths),
      'KS':ks,'max_within_segment_ACF':acf,'uniform_null_KS_p':(1+sum(v>=ks for v in ks_sim))/(reps+1),'uniform_null_ACF_p':(1+sum(v is not None and v>=acf for v in acf_sim))/(reps+1) if acf is not None else None,
      'limitations':['Predictive PIT calibration diagnostic, not parameter uncertainty or causal inference','Not numerically identical to earlier fixed-market parametric-bootstrap p-values','Data/model choice remains exploratory after earlier test inspection']}

def run(reps=499):
    out=OUT/'h3';out.mkdir(parents=True,exist_ok=True)
    with np.load(DATA/'h4_prefix_panel_5min.npz') as a:
        mask=a['t']<PRIMARY_END;t=a['t'][mask];y=a['y'][mask];features=a['X'][mask];names=a['names'].tolist();common=a['old_valid'][mask]&np.isfinite(features).all(axis=1)
    if not len(t) or t[-1]+300!=PRIMARY_END:raise ValueError('Incomplete revised primary clock')
    activity=load(OUT/'activity_readiness.json',{})
    if activity.get('panel_sha256')!=digest(DATA_NEXT/'activity_panel.npz'):raise ValueError('Activity panel not verified')
    with np.load(DATA_NEXT/'activity_panel.npz') as a:
        if not np.array_equal(t,a['t']) or not np.array_equal(y,a['y']):raise ValueError('Activity/target clock mismatch')
        flows=a['X'];past=a['history'];fn=a['names'].tolist();hn=a['history_names'].tolist()
    tr,val,test=masks(t,common);tr &= t>=t[0]+7*86400
    j=feature_groups(names)['oracle_gas'];market=features[:,j];mn=[names[i] for i in j]
    specs={'constant':(np.empty((len(t),0)),[]),'market':(market,mn),'activity':(np.c_[market,flows],mn+fn),'activity_history':(np.c_[market,flows,past],mn+fn+hn)}
    protocol={'created_utc':now(),'ridge_grid':[.0001,.001,.01],'specs':list(specs),'selection':'validation loglik; count-ratio screen 0.5–2 for selection; failed-screen controls retained',
      'activity_panel_sha256':activity['panel_sha256'],'all_models_same_test_mask':True,'test_previously_seen':True,'new_untouched_holdout':False,'target_period_complete':True,'primary_end_exclusive':PRIMARY_END_UTC}
    save(out/'protocol.json',protocol);candidates=[];models={};rows=[];arrays={}
    for name,(raw,labels) in specs.items():
        center=raw[tr].mean(axis=0);scale=raw[tr].std(axis=0);scale[scale==0]=1;X=np.c_[np.ones(len(y)),np.nan_to_num((raw-center)/scale)]
        best=None;fallback=None
        for ridge in protocol['ridge_grid']:
            row={'model':name,'ridge':ridge}
            try:
                params=fit(X,y,tr,ridge);pr=predictions(X[val],params);value=float(score(y[val],pr).sum());ratio=float(pr[-1].sum()/y[val].sum());eligible=.5<=ratio<=2
                row.update(status='eligible' if eligible else 'validation_count_rejected',validation_loglik=value,validation_expected_observed=ratio)
                result=(value,ridge)
                if fallback is None or value>fallback[0]:fallback=result
                if eligible and (best is None or value>best[0]):best=result
            except Exception as exc:row.update(status='failed',error=str(exc))
            candidates.append(row);write(out/'candidates.csv',candidates)
        eligible=best is not None;best=best or fallback
        if best is None:rows.append({'model':name,'status':'no_converged_candidate'});continue
        value,ridge=best;models[name]={'ridge':ridge,'validation_loglik':value,'validation_eligible':eligible,'center':center.tolist(),'scale':scale.tolist(),'labels':labels};save(out/'selection.json',models)
        params=fit(X,y,tr|val,ridge);pr=predictions(X,params);ll=score(y,pr);mean=pr[-1]
        row={'model':name,'status':'completed_exploratory','validation_eligible':eligible,'validation_loglik':value,'test_loglik':float(ll[test].sum()),'test_bins':int(test.sum()),'test_events':int(y[test].sum()),
          'expected_test_events':float(mean[test].sum()),'expected_observed_ratio':float(mean[test].sum()/y[test].sum()),'test_MAE':float(abs(mean[test]-y[test]).mean()),
          'event_Brier':float(((pr[1][test]-(y[test]>0))**2).mean()),'max_expected_bin_count':float(mean[test].max())}
        rows.append(row);models[name].update(event_parameters=params[0].tolist(),size_parameters=params[1].tolist());arrays[name]=(X,pr,ll)
        write(out/'model_comparison.csv',rows);save(out/'fitted_models.json',models);print('HURDLE',name,row['test_loglik'],row['expected_observed_ratio'],flush=True)
    accepted=[r for r in rows if r.get('validation_eligible')]
    selected=max(accepted,key=lambda r:r['validation_loglik'])['model'] if accepted else None;diags={}
    for name in dict.fromkeys([selected,'activity','activity_history']):
        if name in arrays:diags[name]=diagnostics(y,arrays[name][1],np.flatnonzero(test),reps);save(out/'residuals.json',diags);print('PIT',name,diags[name]['uniform_null_KS_p'],flush=True)
    if selected:
        pr=arrays[selected][1];write(out/'heldout_predictions.csv',[{'bin_start_utc':iso(int(t[i])),'observed':int(y[i]),'probability_any_event':float(pr[1][i]),'expected_count':float(pr[-1][i])} for i in np.flatnonzero(test)])
    scope={**load(V2_OUT/'h4_prefix_data_readiness.json')['source'],'end_exclusive':PRIMARY_END_UTC,'events':int(y.sum()),'bins':len(t),'target_end_exclusive':PRIMARY_END_UTC}
    result={'status':'completed_exploratory','updated_utc':now(),'selected_by_validation':selected,'models':len(rows),'test_bins':int(test.sum()),'test_events':int(y[test].sum()),'scope':scope,'target_period_complete':True,
      'diagnostics':diags,'deployment_ready':False,'limitations':['No high-frequency HF/TVL/DEX state; activity counts are context only','Single Aave aggregate target; heterogeneous protocol/token models not yet validated','Hurdle probability and positive-size components are not a structural Hawkes branching process','No event-selected market quotes used as H3 controls','Earlier test already inspected, needs future independent validation']}
    save(out/'summary.json',result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--replications',type=int,default=499);a=p.parse_args()
    with worker_lock(OUT/'hurdle.lock'):print(run(a.replications),flush=True)
