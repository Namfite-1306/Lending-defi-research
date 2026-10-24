"""Predictable market-controlled discrete Hawkes/Poisson count models.

Conditional one-bin-ahead evaluation. Binning is explicit, not a continuous-time
Hawkes estimate; no invented event jitter and no structural causality claim.
"""
import argparse,json,math,time
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from scipy.signal import lfilter
from scipy.special import gammaln,gammaincc,ndtri
from defi_models.core import Data,DEFAULTS,stamp,iso
from .common import SOURCE,OUT,write,save,now

NAMES=['abs_ETH_return_past_hour','down_ETH_return_past_hour','abs_BTC_return_past_hour','down_BTC_return_past_hour','ETH_rv24h','BTC_rv24h','hour_sin','hour_cos']

def history(y,half_life,dt):
    decay=math.exp(-math.log(2)*dt/half_life)
    return lfilter([0,1-decay],[1,-decay],np.asarray(y,float))

def panel(source=SOURCE,bin_minutes=5):
    data=Data(source,DEFAULTS);events=data.read('liquidations_model_table.csv')
    hours=[r for r in data.read('liquidations_hourly_full_period.csv') if r['protocol']=='aave_v3' and r['protocol_deployed']=='True']
    start=stamp(hours[0]['hour_utc']);end=stamp(hours[-1]['hour_utc'])+3600;step=bin_minutes*60
    times=np.array([stamp(r['timestamp_utc']) for r in events if r['protocol']=='aave_v3'])
    y=np.histogram(times,bins=np.arange(start,end+step,step))[0].astype(float);t=start+np.arange(len(y))*step
    if y.sum()!=len(times):raise ValueError('Binned counts do not reconcile')
    feeds={'ETH/USD':{},'BTC/USD':{}}
    for r in data.read('market_prices_hourly_full_period.csv'):
        if r['feed'] not in feeds:continue
        at=stamp(r['timestamp_utc']);source_at=stamp(r['source_update_utc']);price=float(r['price_usd'])
        if source_at>at or price<=0:raise ValueError('Invalid/future price')
        feeds[r['feed']][at]=price if r['stale']=='False' else np.nan
    all_hours=np.arange(start,end,3600);values=[]
    for feed in ['ETH/USD','BTC/USD']:
        p=np.array([feeds[feed].get(at,np.nan) for at in all_hours]);ret=np.r_[np.nan,np.diff(np.log(p))]
        counts=np.convolve(np.isfinite(ret).astype(int),np.ones(24,dtype=int),mode='full')[:len(ret)]
        rv=np.sqrt(np.convolve(np.nan_to_num(ret)**2,np.ones(24),mode='full')[:len(ret)]/24);rv[counts<24]=np.nan
        values.append((ret,rv))
    idx=((t-start)//3600).astype(int);hour=(t%86400)/3600
    X=np.column_stack([np.abs(values[0][0][idx]),np.maximum(-values[0][0][idx],0),np.abs(values[1][0][idx]),np.maximum(-values[1][0][idx],0),
      values[0][1][idx],values[1][1][idx],np.sin(2*np.pi*hour/24),np.cos(2*np.pi*hour/24)])
    valid=np.isfinite(X).all(axis=1)
    return t,y,X,valid,{'start':iso(start),'end_exclusive':iso(end),'events':len(times),'bins':len(y),'bin_minutes':bin_minutes,
      'excluded_covariate_bins':int((~valid).sum()),'inputs':{str(p.relative_to(source)):__import__('research_h124.common',fromlist=['digest']).digest(p) for p in sorted(data.used)}}

def fit(X,y,g,mask,dt,excitation,initial=None):
    A=X[mask];target=y[mask];h=g[mask];k=A.shape[1]
    b=np.zeros(k+int(excitation));b[0]=math.log(max(target.mean()/dt,1e-8))
    if excitation:b[-1]=.2
    if initial is not None and len(initial)==len(b):b=np.array(initial).copy()
    logdt=math.log(dt);factorial=gammaln(target+1)
    def objective(par):
        eta=A@par[:k]+logdt
        # Invalid optimizer trials get a finite smooth continuation. Returned
        # fits are accepted only in the exact exponential region.
        excess=np.maximum(eta-30,0);base=np.exp(np.minimum(eta,30))
        mu=base*(1+excess+excess**2/2);derivative=base*(1+excess)
        mean=mu+(par[-1]*h if excitation else 0);ratio=1-target/mean
        penalty=par[:k].copy();penalty[0]=0;ridge=1e-5
        loss=np.sum(mean-target*np.log(mean)+factorial)+ridge*np.dot(penalty,penalty)/2
        grad=A.T@(ratio*derivative)+ridge*penalty
        if excitation:grad=np.r_[grad,np.dot(ratio,h)]
        return loss/len(target),grad/len(target)
    bounds=[(-20,20)]*k+([(0,.99)] if excitation else [])
    result=minimize(objective,b,jac=True,method='L-BFGS-B',bounds=bounds,options={'maxiter':1000,'ftol':1e-12,'gtol':1e-7,'maxls':100})
    if not result.success:
        result=minimize(objective,result.x,jac=True,method='SLSQP',bounds=bounds,options={'maxiter':1000,'ftol':1e-10})
    if not result.success or not np.isfinite(result.x).all() or np.max(A@result.x[:k]+logdt)>30:raise ValueError('Estimator failed: '+str(result.message))
    return result.x,{'converged':True,'iterations':int(result.nit),'objective':float(result.fun),'message':str(result.message)}

def predict(X,g,par,dt,excitation):
    k=X.shape[1];eta=X@par[:k]+math.log(dt)
    if np.max(eta)>30:raise ValueError('Prediction outside numerical support')
    baseline=np.exp(eta);return baseline+(par[-1]*g if excitation else 0),baseline
def logscore(y,mu):return y*np.log(mu)-mu-gammaln(y+1)
def ks_uniform(u):
    z=np.sort(u);n=len(z);return float(max(np.max(np.arange(1,n+1)/n-z),np.max(z-np.arange(n)/n)))
def residual(y,mu,rng):
    lower=np.where(y>0,gammaincc(y,mu),0);upper=gammaincc(y+1,mu)
    return np.clip(lower+rng.random(len(y))*np.maximum(upper-lower,0),1e-12,1-1e-12)
def maxacf(u,lags=12):
    r=ndtri(u);r-=r.mean();denom=np.dot(r,r)
    return float(max(abs(np.dot(r[:-j],r[j:])/denom) for j in range(1,lags+1))) if denom else 0.

def bootstrap_residual(y,base,g0,eta,half,dt,repetitions=49,seed=42):
    if not repetitions:return {'status':'not_run'}
    rng=np.random.default_rng(seed);decay=math.exp(-math.log(2)*dt/half);h=np.full(repetitions,g0);sim=np.empty((repetitions,len(y)),dtype=np.int32)
    for k,b in enumerate(base):
        sim[:,k]=rng.poisson(b+eta*h);h=decay*h+(1-decay)*sim[:,k]
    obs_mu=base+eta*history(y,half,dt)+eta*g0*decay**np.arange(len(y))
    observed=residual(y,obs_mu,rng);obs_ks=ks_uniform(observed);obs_ac=maxacf(observed)
    ks=[];ac=[]
    for values in sim:
        means=base+eta*history(values,half,dt)+eta*g0*decay**np.arange(len(y))
        u=residual(values,means,rng);ks.append(ks_uniform(u));ac.append(maxacf(u))
    return {'status':'completed_conditional_fixed_parameters','replications':repetitions,'bins':len(y),'KS':obs_ks,'max_abs_acf_lags_1_12':obs_ac,
      'bootstrap_KS_p':(1+sum(k>=obs_ks for k in ks))/(repetitions+1),'bootstrap_acf_p':(1+sum(k>=obs_ac for k in ac))/(repetitions+1),
      'note':'Market path and fitted parameters fixed, no parameter-estimation uncertainty or causal identification; diagnostic p-values.'}

def run(source=SOURCE,out=OUT/'h4',bin_minutes=5,repetitions=49,rolling=True):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);t,y,features,valid,scope=panel(source,bin_minutes);dt=bin_minutes/60
    train_end=stamp('2025-01-01T00:00:00Z');validation_end=stamp('2025-07-01T00:00:00Z')
    train=(t<train_end)&valid&(t>=t[0]+60*3600);validation=(t>=train_end)&(t<validation_end)&valid;test=(t>=validation_end)&valid
    center=features[train].mean(axis=0);scale=features[train].std(axis=0);scale[scale==0]=1
    # Placeholder values below are never scored; complete event history remains
    # in the Hawkes recursion even when market covariates are unavailable.
    standardized=np.nan_to_num((features-center)/scale);market=np.column_stack([np.ones(len(y)),standardized]);constant=np.ones((len(y),1))
    models=[('constant_poisson',False,False),('market_poisson',True,False),('constant_hawkes',False,True),('market_hawkes',True,True)]
    candidates=[];scores=[];fits={};predictions={};diagnostics={};rolling_rows=[];halves=[.25,.5,2.,6.]
    for name,has_market,excitation in models:
        X=market if has_market else constant;best=None
        for half in halves if excitation else [1.]:
            g=history(y,half,dt) if excitation else np.zeros(len(y))
            try:
                par,opt=fit(X,y,g,train,dt,excitation);mu,_=predict(X,g,par,dt,excitation);value=float(logscore(y[validation],mu[validation]).sum())
                item={'model':name,'half_life_hours':half,'validation_loglik':value,'status':'converged',**opt};candidates.append(item)
                if best is None or value>best[0]:best=(value,half,par)
            except ValueError as exc:candidates.append({'model':name,'half_life_hours':half,'status':'failed','error':str(exc)})
        if best is None:raise ValueError('No converged candidate for '+name)
        _,half,initial=best;g=history(y,half,dt) if excitation else np.zeros(len(y));par,opt=fit(X,y,g,train|validation,dt,excitation,initial)
        mu,base=predict(X,g,par,dt,excitation);ll=logscore(y,mu)
        fits[name]={'half_life_hours':half if excitation else None,'parameters':par.tolist(),'eta':float(par[-1]) if excitation else 0.,**opt};predictions[name]=(mu,base,g,ll)
        scores.append({'model':name,'test_bins':int(test.sum()),'test_events':int(y[test].sum()),'test_loglik':float(ll[test].sum()),'mean_test_logscore':float(ll[test].mean()),
          'test_count_MAE':float(np.mean(np.abs(y[test]-mu[test]))),'expected_test_events':float(mu[test].sum()),'eta':fits[name]['eta'],'half_life_hours':fits[name]['half_life_hours']})
        indices=np.flatnonzero(test);groups=np.split(indices,np.where(np.diff(indices)>1)[0]+1);segment=max(groups,key=len)
        diagnostics[name]=bootstrap_residual(y[segment],base[segment],g[segment[0]],fits[name]['eta'],half,dt,repetitions)
        diagnostics[name].update(start_utc=iso(t[segment[0]]),end_exclusive_utc=iso(t[segment[-1]]+bin_minutes*60),scope='longest contiguous valid test segment')
        if rolling:
            for qstart,qend in [('2025-07-01','2025-10-01'),('2025-10-01','2026-01-01'),('2026-01-01','2026-04-01'),('2026-04-01','2026-07-01'),('2026-07-01','2026-10-01')]:
                lo=stamp(qstart+'T00:00:00Z');hi=stamp(qend+'T00:00:00Z');training=(t<lo)&valid&(t>=t[0]+60*3600);evaluation=(t>=lo)&(t<hi)&valid
                rp,_=fit(X,y,g,training,dt,excitation,par);rm,_=predict(X,g,rp,dt,excitation)
                rolling_rows.append({'model':name,'test_start':qstart,'test_end_exclusive':qend,'bins':int(evaluation.sum()),'events':int(y[evaluation].sum()),'loglik':float(logscore(y[evaluation],rm[evaluation]).sum()),'eta':float(rp[-1]) if excitation else 0.})
        print('H4',name,scores[-1]['test_loglik'],'eta',fits[name]['eta'],flush=True)
        write(out/'model_comparison.csv',scores);write(out/'candidates.csv',candidates);save(out/'residuals.json',diagnostics)
    # Paired uncertainty of held-out conditional log-score gain, resampling days.
    delta=predictions['market_hawkes'][3]-predictions['market_poisson'][3];days=(t[test]//86400).astype(int);unique=np.unique(days)
    sums=np.array([delta[test][days==day].sum() for day in unique]);rng=np.random.default_rng(42)
    boot=sums[rng.integers(0,len(sums),size=(500,len(sums)))].sum(axis=1)
    comparison={'market_hawkes_minus_market_poisson_test_loglik':float(sums.sum()),'day_resampling_95_interval':np.quantile(boot,[.025,.975]).tolist(),
      'note':'Fixed fitted models, iid daily-block resampling; not a parameter or structural-causality confidence interval.'}
    write(out/'rolling_quarter_scores.csv',rolling_rows)
    test_indices=np.flatnonzero(test);output=[]
    for i in test_indices:
        row={'bin_start_utc':iso(t[i]),'observed':int(y[i])}
        for name,(mu,base,g,ll) in predictions.items():row[name]=float(mu[i])
        output.append(row)
    write(out/'heldout_predictions.csv',output)
    summary={'status':'completed_scoped','generated_utc':now(),'scope':scope,'train_end_exclusive':iso(train_end),'validation_end_exclusive':iso(validation_end),
      'prediction':'conditional next-bin count given market information available at bin start and observed prior events',
      'feature_names':NAMES,'training_center':center.tolist(),'training_scale':scale.tolist(),'models':fits,'comparison':comparison,
      'limitations':['Discrete binned Hawkes approximation, not sub-block continuous-time intensity','Kernel grid selected on validation only; test untouched until final evaluation',
        'Conditional predictions use actual previous test events; not an open-loop multi-step forecast','Residual bootstrap fixes market path and parameters; does not include estimation uncertainty',
        'Predictive excitation may still reflect omitted common factors and protocol changes; not strict structural causation','Oracle hourly market controls do not measure all CEX/DEX conditions']}
    save(out/'summary.json',summary);return summary

def main():
    p=argparse.ArgumentParser();p.add_argument('--bin-minutes',type=int,choices=[5,15,60],default=5);p.add_argument('--bootstrap',type=int,default=49);p.add_argument('--no-rolling',action='store_true');a=p.parse_args()
    if not 0<=a.bootstrap<=499:p.error('Invalid bootstrap count')
    run(out=OUT/('h4' if a.bin_minutes==5 else f'h4_{a.bin_minutes}min'),bin_minutes=a.bin_minutes,repetitions=a.bootstrap,rolling=not a.no_rolling)
if __name__=='__main__':main()
