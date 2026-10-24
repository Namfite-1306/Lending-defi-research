"""Small explicit estimators with chronological evaluation and convergence reporting."""
import numpy as np
from scipy.optimize import minimize
from scipy.special import expit,gammaln

def poisson_terms(eta):
    """Convex smooth continuation only for extreme optimizer trials; exact below 30."""
    eta=np.asarray(eta,float);excess=np.maximum(eta-30,0);base=np.exp(np.minimum(eta,30))
    return base*(1+excess+excess**2/2),base*(1+excess)

def poisson_predict(X,b):
    eta=np.asarray(X)@b
    if not np.isfinite(eta).all() or np.max(eta)>30:raise ValueError('Poisson predictor outside numerical support; inspect covariates instead of clipping predictions')
    return np.exp(eta)

def glm(X,y,family='poisson',ridge=1e-6):
    X=np.asarray(X,float);y=np.asarray(y,float)
    if X.ndim!=2 or len(y)!=len(X) or not len(y) or not np.isfinite(X).all() or not np.isfinite(y).all():raise ValueError('Invalid GLM inputs')
    if family not in ('poisson','logistic') or np.any(y<0) or (family=='logistic' and np.any(y>1)):raise ValueError('Invalid GLM family/outcome')
    def objective(b):
        eta=X@b
        if family=='poisson':
            value,derivative=poisson_terms(eta);loss=np.sum(value-y*eta+gammaln(y+1));grad=X.T@(derivative-y)
        else:
            mu=expit(eta);loss=np.sum(np.logaddexp(0,eta)-y*eta);grad=X.T@(mu-y)
        penalty=b.copy();penalty[0]=0
        return loss+ridge*np.dot(penalty,penalty)/2,grad+ridge*penalty
    fit=minimize(objective,np.zeros(X.shape[1]),jac=True,method='L-BFGS-B',bounds=[(-20,20)]*X.shape[1],options={'maxiter':500,'ftol':1e-11})
    mu=poisson_predict(X,fit.x) if family=='poisson' else expit(X@fit.x)
    return fit,mu

def poisson_deviance(y,mu):
    y=np.asarray(y);mu=np.maximum(mu,1e-15);positive=y>0
    term=np.zeros_like(mu);term[positive]=y[positive]*np.log(y[positive]/mu[positive])
    return 2*np.sum(term-(y-mu))

def hawkes_history(times,beta):
    """All events tied to one block timestamp share pre-group intensity; no invented jitter."""
    t,counts=np.unique(times,return_counts=True);h=np.zeros(len(t))
    for i in range(1,len(t)):h[i]=(h[i-1]+counts[i-1])*np.exp(-beta*(t[i]-t[i-1]))
    return t,counts,h

def hawkes_score(t,m,h,mu,eta,beta,start,end):
    mask=(t>=start)&(t<end);prior=t<end
    # Integrated kernel contribution from all observed events, including train history.
    integral=np.sum(m[prior]*(np.exp(-beta*np.maximum(start-t[prior],0))-np.exp(-beta*(end-t[prior]))))
    return np.sum(m[mask]*np.log(mu+eta*beta*h[mask]))-mu*(end-start)-eta*integral

def hawkes_fit(times,end,train_end,half_lives):
    times=np.asarray(times,float)
    if not len(times) or not np.isfinite(times).all() or np.any(times<0) or np.any(times>=end) or not 0<train_end<end:raise ValueError('Events outside Hawkes observation interval')
    out=[];best=None
    for half in half_lives:
        beta=np.log(2)/half;t,m,h=hawkes_history(times,beta);train=t<train_end
        comp=np.sum(m[train]*(1-np.exp(-beta*(train_end-t[train]))))
        def f(x):
            mu,eta=x;lam=mu+eta*beta*h[train];weight=m[train]/lam
            value=mu*train_end+eta*comp-np.sum(m[train]*np.log(lam))
            return value,np.array([train_end-weight.sum(),comp-np.sum(weight*beta*h[train])])
        fit=minimize(f,[max(m[train].sum()/train_end/2,1e-8),.3],jac=True,bounds=[(1e-10,None),(0,.99)],method='L-BFGS-B',options={'maxiter':400})
        mu,eta=fit.x
        train_ll=-fit.fun;test_ll=hawkes_score(t,m,h,mu,eta,beta,train_end,end)
        item=dict(half_life_hours=half,beta_per_hour=beta,baseline_per_hour=mu,branching_ratio=eta,
                  train_loglik=train_ll,test_loglik=test_ll,aic=6-2*train_ll,converged=bool(fit.success),message=str(fit.message))
        out.append(item)
        if fit.success and (best is None or item['train_loglik']>best['train_loglik']):best=item
    return best,out

def breakpoint(x,y):
    """Descriptive continuous one-knot least squares; no causal/significance claim."""
    x=np.asarray(x);y=np.asarray(y);base=np.column_stack([np.ones(len(x)),x]);b=np.linalg.lstsq(base,y,rcond=None)[0]
    base_sse=np.sum((base@b-y)**2);best=None
    if len(x)<7 or np.ptp(y)==0:return {'identified':False,'reason':'flat response or fewer than seven grid points'}
    for knot in x[2:-2]:
        X=np.column_stack([base,np.maximum(0,x-knot)]);coef=np.linalg.lstsq(X,y,rcond=None)[0];sse=np.sum((X@coef-y)**2)
        if best is None or sse<best['sse']:best=dict(knot=float(knot),sse=float(sse),coefficients=coef.tolist())
    return dict(identified=True,linear_sse=float(base_sse),**best)
