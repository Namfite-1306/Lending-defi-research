"""Negative-binomial innovation sensitivity for overdispersed Hawkes counts.

Separate from primary four Poisson-family models. No structural causality claim.
"""
import argparse,math
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln,digamma,betainc
from .h4 import panel,history,NAMES,ks_uniform,maxacf
from defi_models.core import stamp,iso
from .common import OUT,write,save,now

def nb_objective(par,X,y,g,dt,excitation):
    k=X.shape[1];eta=X@par[:k]+math.log(dt);excess=np.maximum(eta-30,0);base=np.exp(np.minimum(eta,30))
    derivative=base*(1+excess);baseline=base*(1+excess+excess**2/2);mu=baseline+(par[k]*g if excitation else 0);r=math.exp(par[-1])
    ll=gammaln(y+r)-gammaln(r)-gammaln(y+1)+r*(math.log(r)-np.log(r+mu))+y*(np.log(mu)-np.log(r+mu))
    dm=r*(mu-y)/(mu*(r+mu));grad=X.T@(dm*derivative)
    if excitation:grad=np.r_[grad,np.dot(dm,g)]
    dr=-(digamma(y+r)-digamma(r)+math.log(r)+1-np.log(r+mu)-(r+y)/(r+mu))
    grad=np.r_[grad,np.sum(dr)*r]
    penalty=par[:k].copy();penalty[0]=0;grad[:k]+=1e-5*penalty
    return (-ll.sum()+1e-5*np.dot(penalty,penalty)/2)/len(y),grad/len(y)

def fit(X,y,g,mask,dt,excitation,initial=None):
    k=X.shape[1];b=np.zeros(k+int(excitation)+1);b[0]=math.log(max(y[mask].mean()/dt,1e-8));b[-1]=-1
    if excitation:b[k]=.2
    if initial is not None:b=np.array(initial).copy()
    bounds=[(-8,8)]*k+([(0,.99)] if excitation else [])+[(-8,10)]
    f=lambda par:nb_objective(par,X[mask],y[mask],g[mask],dt,excitation)
    result=minimize(f,b,jac=True,bounds=bounds,method='L-BFGS-B',options={'maxiter':1000,'ftol':1e-12,'gtol':1e-7,'maxls':100})
    if not result.success:result=minimize(f,result.x,jac=True,bounds=bounds,method='SLSQP',options={'maxiter':1000,'ftol':1e-10})
    if not result.success:raise ValueError('NB optimizer: '+str(result.message))
    if np.max(X@result.x[:k]+math.log(dt))>30:raise ValueError('NB prediction outside support')
    return result.x
def prediction(X,g,par,dt,excitation):
    k=X.shape[1];mu=np.exp(X@par[:k])*dt+(par[k]*g if excitation else 0);return mu,math.exp(par[-1])
def score(y,mu,r):return gammaln(y+r)-gammaln(r)-gammaln(y+1)+r*(math.log(r)-np.log(r+mu))+y*(np.log(mu)-np.log(r+mu))

def pit(y,mu,r,rng):
    p=r/(r+mu);lower=np.where(y>0,betainc(r,y,p),0);upper=betainc(r,y+1,p)
    return np.clip(lower+rng.random(len(y))*np.maximum(upper-lower,0),1e-12,1-1e-12)

def bootstrap(y,baseline,g0,eta,r,half,dt,repetitions=49):
    rng=np.random.default_rng(42);decay=math.exp(-math.log(2)*dt/half);h=np.full(repetitions,g0);sim=np.empty((repetitions,len(y)),dtype=np.int64)
    for i,b in enumerate(baseline):
        mean=b+eta*h;draw=rng.negative_binomial(r,r/(r+mean))
        if np.any(draw<0):raise ValueError('NB simulation exceeded count support')
        sim[:,i]=draw;h=decay*h+(1-decay)*draw
    means=baseline+eta*history(y,half,dt)+eta*g0*decay**np.arange(len(y));u=pit(y,means,r,rng);observed_ks=ks_uniform(u);observed_acf=maxacf(u);ks=[];acf=[]
    for row in sim:
        mean=baseline+eta*history(row,half,dt)+eta*g0*decay**np.arange(len(y));u=pit(row,mean,r,rng);ks.append(ks_uniform(u));acf.append(maxacf(u))
    return {'replications':repetitions,'bins':len(y),'KS':observed_ks,'max_abs_acf_lags_1_12':observed_acf,
      'bootstrap_KS_p':(1+sum(x>=observed_ks for x in ks))/(repetitions+1),'bootstrap_acf_p':(1+sum(x>=observed_acf for x in acf))/(repetitions+1),
      'scope':'longest contiguous valid test segment, fixed fitted parameters and observed market path; not causal identification'}

def run(bin_minutes=5):
    out=OUT/('h4_nb' if bin_minutes==5 else f'h4_nb_{bin_minutes}min');out.mkdir(parents=True,exist_ok=True)
    t,y,features,valid,scope=panel(bin_minutes=bin_minutes);dt=bin_minutes/60
    train=(t<stamp('2025-01-01T00:00:00Z'))&valid&(t>=t[0]+60*3600)
    validation=(t>=stamp('2025-01-01T00:00:00Z'))&(t<stamp('2025-07-01T00:00:00Z'))&valid;test=(t>=stamp('2025-07-01T00:00:00Z'))&valid
    center=features[train].mean(axis=0);scale=features[train].std(axis=0);scale[scale==0]=1;X=np.column_stack([np.ones(len(y)),np.nan_to_num((features-center)/scale)])
    rows=[];candidates=[];fits={};diagnostics={};rng=np.random.default_rng(42);likelihoods={}
    for name,exc in [('market_nb_no_excitation',False),('market_nb_hawkes',True)]:
        best=None
        for half in [.25,.5,2,6] if exc else [1.]:
            g=history(y,half,dt) if exc else np.zeros(len(y))
            try:
                par=fit(X,y,g,train,dt,exc);mu,r=prediction(X,g,par,dt,exc);ll=float(score(y[validation],mu[validation],r).sum())
                candidates.append({'model':name,'half_life_hours':half,'validation_loglik':ll,'converged':True})
                if best is None or ll>best[0]:best=(ll,half,par)
            except ValueError as error:candidates.append({'model':name,'half_life_hours':half,'converged':False,'error':str(error)})
        if best is None:raise ValueError('No NB candidate converged')
        _,half,par=best;g=history(y,half,dt) if exc else np.zeros(len(y));par=fit(X,y,g,train|validation,dt,exc,par);mu,r=prediction(X,g,par,dt,exc)
        target=y[test];means=mu[test];p=r/(r+means);lower=np.where(target>0,betainc(r,target,p),0);upper=betainc(r,target+1,p)
        u=np.clip(lower+rng.random(len(target))*np.maximum(upper-lower,0),1e-12,1-1e-12)
        rows.append({'model':name,'test_loglik':float(score(target,means,r).sum()),'test_MAE':float(np.abs(target-means).mean()),
          'expected_events':float(means.sum()),'observed_events':int(target.sum()),'eta':float(par[X.shape[1]]) if exc else 0.,'dispersion_r':r,
          'half_life_hours':half if exc else None,'PIT_KS_descriptive':ks_uniform(u),'PIT_max_abs_ACF_descriptive':maxacf(u)})
        likelihoods[name]=score(target,means,r);indices=np.flatnonzero(test);segments=np.split(indices,np.where(np.diff(indices)>1)[0]+1);segment=max(segments,key=len)
        baseline=np.exp(X@par[:X.shape[1]])*dt
        diagnostics[name]=bootstrap(y[segment],baseline[segment],g[segment[0]],float(par[X.shape[1]]) if exc else 0,r,half,dt)
        fits[name]=par.tolist();print('H4 NB',name,rows[-1],flush=True)
    write(out/'model_comparison.csv',rows);write(out/'candidates.csv',candidates)
    save(out/'residuals.json',diagnostics)
    delta=likelihoods['market_nb_hawkes']-likelihoods['market_nb_no_excitation'];days=(t[test]//86400).astype(int)
    sums=np.array([delta[days==day].sum() for day in np.unique(days)]);rng=np.random.default_rng(42);resampled=sums[rng.integers(0,len(sums),(500,len(sums)))].sum(axis=1)
    save(out/'paired_logscore.json',{'gain':float(delta.sum()),'daily_resampling_95_interval':np.quantile(resampled,[.025,.975]).tolist(),'scope':'fixed fits, daily score blocks; not causal or parameter CI'})
    save(out/'summary.json',{'status':'completed_sensitivity','generated_utc':now(),'scope':scope,'models':fits,'features':NAMES,
      'training_center':center.tolist(),'training_scale':scale.tolist(),'test':'2025-07-01 through before 2026-10-01',
      'limitations':['Discrete-time conditional NB innovations, not a continuous-time point process','Residual bootstrap fixes parameters and market path; parameter uncertainty omitted',
        'Shared market path and omitted variables still prevent structural causality','Do not compare bin sizes using raw total likelihood']})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bin-minutes',type=int,choices=[5,15],default=5);a=p.parse_args();run(a.bin_minutes)
