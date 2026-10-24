"""Regularized count models and predictable long-run background sensitivity.

Softplus is a model link, not a cap applied to predictions. Only validation
selects hyperparameters; outputs remain exploratory because earlier test seen.
"""
import argparse,math
import numpy as np
from scipy.optimize import minimize
from scipy.special import expit,gammaln,digamma
from .repair_common import *
from .h4 import history,logscore,residual,ks_uniform
from .h4_nb import score as nb_score,pit as nb_pit
from .h4_extended import feature_groups
from .residual_v2 import segmented_acf
from defi_models.core import stamp,iso

DT=1/12
LONG_HALF=168.

def link(z,kind):
    if kind=='softplus':return np.logaddexp(0,z)+1e-9,expit(z)
    if np.any(z>40):raise ValueError('Exponential link outside numerical support')
    value=np.exp(z);return value,value

def objective(par,X,y,g,kind,family,excitation,ridge):
    k=X.shape[1];baseline,derivative=link(X@par[:k],kind);mu=baseline*DT+(par[k]*g if excitation else 0)
    if family=='poisson':ll=logscore(y,mu);d=1-y/mu
    else:
        r=math.exp(par[-1]);ll=nb_score(y,mu,r);d=r*(mu-y)/(mu*(r+mu))
    grad=X.T@(d*derivative*DT)/len(y)
    if excitation:grad=np.r_[grad,float(d@g)/len(y)]
    if family=='nb':
        dr=-(digamma(y+r)-digamma(r)+math.log(r)+1-np.log(r+mu)-(r+y)/(r+mu))
        grad=np.r_[grad,float(dr.mean()*r)]
    penalty=par[:k].copy();penalty[0]=0;grad[:k]+=ridge*penalty
    return float(-ll.mean()+ridge*(penalty@penalty)/2),grad

def fit(X,y,g,mask,kind,family,excitation,ridge,initial=None):
    A=X[mask];v=y[mask];h=g[mask];k=A.shape[1];rate=max(v.mean()/DT,1e-6)
    par=np.zeros(k+int(excitation)+int(family=='nb'));par[0]=math.log(rate) if kind=='exp' else (rate if rate>20 else math.log(math.expm1(rate)))
    if excitation:par[k]=.2
    if family=='nb':par[-1]=-1
    if initial is not None:par=np.array(initial).copy()
    bounds=[(-20,20)]*k+([(0,.99)] if excitation else [])+([(-8,8)] if family=='nb' else [])
    def loss(p):
        try:return objective(p,A,v,h,kind,family,excitation,ridge)
        except ValueError:return 1e100,np.zeros_like(p)
    opt=minimize(loss,par,jac=True,bounds=bounds,method='L-BFGS-B',options={'maxiter':700,'ftol':1e-11,'gtol':1e-7,'maxls':60})
    if not opt.success:raise ValueError('Fit did not converge: '+str(opt.message))
    _,grad=loss(opt.x)
    if not np.isfinite(opt.x).all():raise ValueError('Nonfinite fitted parameters')
    return opt.x,{'iterations':int(opt.nit),'gradient_max':float(abs(grad).max()),'coefficient_at_bound':bool(np.any(abs(opt.x[:k])>19.999))}

def predict(X,g,par,kind,family,excitation):
    k=X.shape[1];rate,_=link(X@par[:k],kind);mu=DT*rate+(par[k]*g if excitation else 0)
    if not np.isfinite(mu).all() or np.any(mu<=0):raise ValueError('Invalid predictive mean')
    return mu,math.exp(par[-1]) if family=='nb' else None

def point_scores(y,mu,family,r):return logscore(y,mu) if family=='poisson' else nb_score(y,mu,r)

def masks(t,common):
    return ((t<stamp('2025-01-01T00:00:00Z'))&common&(t>=t[0]+60*3600),
      (t>=stamp('2025-01-01T00:00:00Z'))&(t<stamp('2025-07-01T00:00:00Z'))&common,
      (t>=stamp('2025-07-01T00:00:00Z'))&common)

def bootstrap_dynamic(y,X,g,long_state,indices,par,kind,family,excitation,half,adaptive,center,scale,reps=199):
    """Both history states evolve from each simulated path, resetting only at gaps."""
    segments=np.split(indices,np.where(np.diff(indices)>1)[0]+1);lengths=[len(s) for s in segments]
    k=X.shape[1];eta=float(par[k]) if excitation else 0.;r=math.exp(par[-1]) if family=='nb' else None
    expected,_=predict(X,g,par,kind,family,excitation);rng=np.random.default_rng(42)
    u=residual(y[indices],expected[indices],rng) if r is None else nb_pit(y[indices],expected[indices],r,rng)
    observed_ks=ks_uniform(u);observed_acf=segmented_acf(u,lengths);ks=[];acf=[]
    decay=math.exp(-math.log(2)*DT/half);slow_decay=math.exp(-math.log(2)*DT/LONG_HALF)
    # At most 25 paths in memory, including large production holdouts.
    for batch_start in range(0,reps,25):
        count=min(25,reps-batch_start);draws=np.empty((count,len(indices)),dtype=np.int64);means=np.empty_like(draws,dtype=float);offset=0
        exog=X@par[:k]
        if adaptive:exog=exog-X[:,-1]*par[k-1]
        for seg in segments:
            fast=np.full(count,g[seg[0]]);slow=np.full(count,long_state[seg[0]])
            for j in seg:
                z=exog[j]+(par[k-1]*(np.log1p(slow)-center[-1])/scale[-1] if adaptive else 0)
                rate,_=link(z,kind);mu=rate*DT+eta*fast
                values=rng.poisson(mu) if r is None else rng.negative_binomial(r,r/(r+mu))
                draws[:,offset]=values;means[:,offset]=mu;offset+=1
                fast=decay*fast+(1-decay)*values;slow=slow_decay*slow+(1-slow_decay)*values
        for values,mu in zip(draws,means):
            u=residual(values,mu,rng) if r is None else nb_pit(values,mu,r,rng)
            ks.append(ks_uniform(u));acf.append(segmented_acf(u,lengths))
        print('BOOTSTRAP',batch_start+count,'/',reps,flush=True)
    return {'status':'completed_all_valid_segments','replications':reps,'bins':len(indices),'segments':len(segments),'KS':observed_ks,'max_abs_within_segment_ACF':observed_acf,
      'bootstrap_KS_p':(1+sum(v>=observed_ks for v in ks))/(reps+1),
      'bootstrap_acf_p':(1+sum(v is not None and v>=observed_acf for v in acf))/(reps+1) if observed_acf is not None else None,
      'fraction_test_bins_checked':1.,'dynamic_slow_background_resimulated':adaptive,
      'scope':'Fixed parameters/exogenous market path; both short and slow event states resimulated; reset from observed history at each gap; not causal identification'}

def run(reps=199):
    out=OUT/'h3';out.mkdir(parents=True,exist_ok=True);path=DATA/'h4_prefix_panel_5min.npz';ready=load(V2_OUT/'h4_prefix_data_readiness.json',{})
    if ready.get('panel_sha256')!=digest(path):raise ValueError('Panel integrity mismatch')
    with np.load(path) as a:t=a['t'];y=a['y'];features=a['X'];names=a['names'].tolist();common=a['old_valid']&np.isfinite(features).all(axis=1)
    train,val,test=masks(t,common);long_state=history(y,LONG_HALF,DT);groups=feature_groups(names);base=features[:,groups['oracle_gas']];base_names=[names[j] for j in groups['oracle_gas']]
    frozen={'created_utc':now(),'scope':ready['source'],'test_previously_seen':True,'panel_sha256':digest(path),'ridge_grid':[.0001,.001,.01],
      'architecture_grid':['exp_regularized','softplus','softplus_adaptive'],'families':['poisson','nb'],'kernel_half_life_hours':[.25,.5,2],
      'validation_count_ratio_screen':[.5,2],'selection':'highest validation log-score among converged candidates passing count-ratio screen; never test',
      'slow_half_life_hours':LONG_HALF,'bootstrap_replications':reps,'no_output_clipping':True}
    save(out/'protocol.json',frozen);candidates=[];comparisons=[];fitted={};arrays={};g_hist={h:history(y,h,DT) for h in [.25,.5,2]};zero=np.zeros(len(y))
    for architecture in frozen['architecture_grid']:
        adaptive=architecture=='softplus_adaptive';kind='exp' if architecture=='exp_regularized' else 'softplus'
        raw=np.c_[base,np.log1p(long_state)] if adaptive else base
        labels=base_names+(['log1p_predictable_7day_background'] if adaptive else [])
        center=raw[train].mean(axis=0);scale=raw[train].std(axis=0);scale[scale==0]=1;X=np.c_[np.ones(len(y)),np.nan_to_num((raw-center)/scale)]
        for family in ['poisson','nb']:
          for excitation in [False,True]:
            model=architecture+'_'+family+('_hawkes' if excitation else '_background');best=None;best_converged=None
            for ridge in frozen['ridge_grid']:
              for half in frozen['kernel_half_life_hours'] if excitation else [1.]:
                g=g_hist[half] if excitation else zero;row={'model':model,'ridge':ridge,'half_life_hours':half}
                try:
                    par,opt=fit(X,y,g,train,kind,family,excitation,ridge);mu,r=predict(X[val],g[val],par,kind,family,excitation)
                    value=float(point_scores(y[val],mu,family,r).sum());ratio=float(mu.sum()/y[val].sum());accepted=.5<=ratio<=2
                    row.update(status='eligible' if accepted else 'rejected_validation_count_ratio',validation_loglik=value,validation_expected_observed=ratio,**opt)
                    if best_converged is None or value>best_converged[0]:best_converged=(value,ridge,half,par)
                    if accepted and (best is None or value>best[0]):best=(value,ridge,half,par)
                except Exception as exc:row.update(status='failed',error=str(exc))
                candidates.append(row);write(out/'candidates.csv',candidates)
            eligible=best is not None
            if best is None:best=best_converged
            if best is None:comparisons.append({'model':model,'status':'no_converged_validation_candidate'});write(out/'model_comparison.csv',comparisons);continue
            value,ridge,half,initial=best;g=g_hist[half] if excitation else zero
            # Save the selected validation decision before evaluating the test.
            fitted[model]={'architecture':architecture,'kind':kind,'family':family,'excitation':excitation,'ridge':ridge,'half':half,'validation_loglik':value,'validation_eligible':eligible,'labels':labels,'center':center.tolist(),'scale':scale.tolist()}
            save(out/'selected_hyperparameters.json',fitted)
            try:par,opt=fit(X,y,g,train|val,kind,family,excitation,ridge,initial);mu,r=predict(X,g,par,kind,family,excitation)
            except Exception as exc:comparisons.append({'model':model,'status':'refit_failed','error':str(exc)});write(out/'model_comparison.csv',comparisons);continue
            ll=point_scores(y,mu,family,r);ratio=float(mu[test].sum()/y[test].sum())
            row={'model':model,'status':'completed_exploratory','validation_loglik':value,'test_loglik':float(ll[test].sum()),'test_count_MAE':float(abs(y[test]-mu[test]).mean()),
              'test_bins':int(test.sum()),'test_events':int(y[test].sum()),'expected_test_events':float(mu[test].sum()),'expected_observed_ratio':ratio,
              'test_max_expected_count':float(mu[test].max()),'top10_prediction_share':float(np.sort(mu[test])[-10:].sum()/mu[test].sum()),'eta':float(par[X.shape[1]]) if excitation else 0.,'dispersion_r':r,'ridge':ridge,**opt}
            row['validation_eligible']=eligible
            comparisons.append(row);fitted[model]['parameters']=par.tolist();arrays[model]=(X,g,par,mu,ll,adaptive,center,scale)
            write(out/'model_comparison.csv',comparisons);save(out/'fitted_models.json',fitted);print('REPAIR H3',model,row['test_loglik'],ratio,flush=True)
    completed=[r for r in comparisons if r['status']=='completed_exploratory' and r.get('validation_eligible')]
    if not completed:raise ValueError('No completed validation-selected models')
    selected=max(completed,key=lambda r:r['validation_loglik'])['model'];spec=fitted[selected]
    paired=spec['architecture']+'_'+spec['family']+('_background' if spec['excitation'] else '_hawkes')
    diagnostics={};rolling=[]
    for model in dict.fromkeys([selected,paired,'softplus_adaptive_poisson_hawkes','softplus_adaptive_poisson_background']):
        if model not in arrays:continue
        X,g,par,mu,ll,adaptive,center,scale=arrays[model];f=fitted[model]
        diagnostics[model]=bootstrap_dynamic(y,X,g,long_state,np.flatnonzero(test),par,f['kind'],f['family'],f['excitation'],f['half'],adaptive,center,scale,reps)
        save(out/'residuals.json',diagnostics)
        for lo,hi in [('2025-07-01','2025-10-01'),('2025-10-01','2026-01-01'),('2026-01-01','2026-04-01'),('2026-04-01','2026-07-01'),('2026-07-01','2026-10-01')]:
            lower=stamp(lo+'T00:00:00Z');upper=stamp(hi+'T00:00:00Z');tr=(t<lower)&common&(t>=t[0]+60*3600);te=(t>=lower)&(t<upper)&common
            row={'model':model,'requested_start':lo,'requested_end_exclusive':hi,'bins':int(te.sum())}
            if not te.any():row.update(status='no_scored_bins',loglik=None)
            else:
                p,_=fit(X,y,g,tr,f['kind'],f['family'],f['excitation'],f['ridge'],par);prediction,r=predict(X,g,p,f['kind'],f['family'],f['excitation'])
                row.update(status='partial_quarter' if t[te][-1]+300<upper else 'scored',actual_end_exclusive=iso(int(t[te][-1]+300)),events=int(y[te].sum()),loglik=float(point_scores(y[te],prediction[te],f['family'],r).sum()),expected_observed_ratio=float(prediction[te].sum()/y[te].sum()))
            rolling.append(row)
        write(out/'rolling_quarter_scores.csv',rolling)
    indices=np.flatnonzero(test);mu=arrays[selected][3]
    write(out/'heldout_predictions.csv',[{'bin_start_utc':iso(int(t[i])),'observed':int(y[i]),'selected_expected':float(mu[i])} for i in indices])
    # Extrapolation diagnostics, calculated against train only, do not tune the model.
    domain=[{'feature':n,'train_min':float(base[train,j].min()),'train_max':float(base[train,j].max()),'test_min':float(base[test,j].min()),'test_max':float(base[test,j].max()),'test_outside_train_bins':int(((base[test,j]<base[train,j].min())|(base[test,j]>base[train,j].max())).sum())} for j,n in enumerate(base_names)]
    write(out/'extrapolation.csv',domain)
    ci=None
    if paired in arrays:
        gain=arrays[selected][4][test]-arrays[paired][4][test];days=t[test]//86400;daily=np.array([gain[days==d].sum() for d in np.arange(days.min(),days.max()+1)])
        rng=np.random.default_rng(42);boot=[];block=7
        for _ in range(499):
            starts=rng.integers(0,max(1,len(daily)-block+1),math.ceil(len(daily)/block));sample=np.concatenate([daily[s:s+block] for s in starts])[:len(daily)];boot.append(sample.sum())
        ci={'selected_minus_pair_test_logscore':float(gain.sum()),'seven_day_block_resampling_95':np.quantile(boot,[.025,.975]).tolist(),'fixed_fits':True,'not_causal_or_preregistered':True}
    summary={'status':'completed_exploratory','updated_utc':now(),'selected_by_validation':selected,'paired_model':paired,'scope':ready['source'],'target_period_complete':False,
      'common_bins':int(common.sum()),'test_bins':int(test.sum()),'test_events':int(y[test].sum()),'test_event_coverage':float(y[test].sum()/y[t>=stamp('2025-07-01T00:00:00Z')].sum()),
      'pair_comparison':ci,'diagnostics':diagnostics,'deployment_ready':False,
      'limitations':['Repair hypotheses informed by previous test failures: exploratory, needs a new untouched period','Softplus is a link model, not prediction clipping',
        '7-day background is a predictable count-history proxy, not observed TVL/debt/HF; background comparator still uses slow history',
        'Bootstrap fixes fitted parameters and market path; both endogenous history states resimulated','No causal contagion identification; incomplete target period','Independent market prices and high-frequency HF/DEX controls still missing']}
    save(out/'summary.json',summary);return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bootstrap',type=int,default=199);a=p.parse_args()
    with worker_lock(OUT/'h3.lock'):print(run(a.bootstrap),flush=True)
