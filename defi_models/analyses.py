"""RQ1/RQ4 estimators; compatibility imports for extracted member modules."""
import math
from collections import defaultdict
import numpy as np
from .core import rows,write_csv,stamp,iso,require,summary,shock_grid
from .statistics import breakpoint,glm,poisson_deviance,hawkes_fit,poisson_predict
from .rq3 import rq3, temporal_positive
from .rq2_rq5 import rq2, rq5

def rq1(data,out,cfg):
    p,scope=data.snapshot();write_csv(out/'factor_mapping.csv',p.mapping());results=[];breaks=[]
    grid=shock_grid(cfg['shock_max'],cfg['shock_step'])
    baseline,_=p.stress();already=baseline<1
    for scenario in ['ETH_only','BTC_only','ETH_BTC_joint']:
        series=[]
        for s in grid:
            hf,debt=p.stress(s if scenario!='BTC_only' else 0,s if scenario!='ETH_only' else 0)
            eligible=(hf<1)&(debt>0)
            row=dict(scenario=scenario,shock_fraction=float(s),eligible_wallets=int(eligible.sum()),newly_eligible_wallets=int((eligible&~already).sum()),
                     eligible_risk_debt_usd=float(debt[eligible].sum()),total_risk_debt_usd=float(debt.sum()))
            series.append(row);results.append(row)
        y=np.array([r['eligible_risk_debt_usd'] for r in series]);j=int(np.argmax(np.diff(y)))
        breaks.append(dict(scenario=scenario,largest_grid_increment_start=float(grid[j]),largest_grid_increment_end=float(grid[j+1]),
                           largest_increment_usd=float(y[j+1]-y[j]),piecewise=breakpoint(grid,y)))
    write_csv(out/'stress_curve.csv',results)
    return summary('ready_scoped','Static eligible debt under explicit factor shocks, not executed liquidations',
        ['Single snapshot; endogenous price impact not included','Derivative factors assume one-to-one sensitivity; depeg/basis not estimated',
         'Float64 aggregate scenario calculation; not a Solidity liquidation transaction replica'],snapshot=scope,breakpoints=breaks,
         baseline_eligible_wallets=int(already.sum()))

def rq4(data,out,cfg):
    proto=cfg['protocol'];panel=[r for r in data.read('liquidations_hourly_full_period.csv') if r['protocol']==proto and r['protocol_deployed']=='True']
    require(len(panel)>240,'Need more than 240 deployed hourly observations')
    panel.sort(key=lambda r:r['hour_utc']);start=stamp(panel[0]['hour_utc']);end=stamp(panel[-1]['hour_utc'])+3600
    require(all(stamp(r['hour_utc'])==start+i*3600 for i,r in enumerate(panel)),'Hourly count panel has gaps/duplicates')
    times=sorted(stamp(r['timestamp_utc']) for r in data.read('liquidations_model_table.csv') if r['protocol']==proto)
    require(len(times)>20,'Too few liquidation events')
    event_times=(np.asarray(times)-start)/3600;T=(end-start)/3600;split=int(T*cfg['train_fraction'])
    require(len(event_times[event_times<split])>10 and len(event_times[event_times>=split])>0,'Insufficient train/test events')
    best,candidates=hawkes_fit(event_times,T,split,cfg['hawkes_half_lives_hours']);write_csv(out/'hawkes_candidates.csv',candidates)
    price=defaultdict(dict)
    for r in rows(data.path('market_prices_hourly_full_period.csv')):
        if r['feed'] in ['ETH/USD','BTC/USD']:
            at=stamp(r['timestamp_utc']);value=float(r['price_usd'])
            require(at not in price[r['feed']],'Duplicate hourly feed observation')
            require(math.isfinite(value) and value>0 and stamp(r['source_update_utc'])<=at,'Invalid/future market price')
            price[r['feed']][at]=(value,r['stale']=='True')
    y=np.array([int(r['liquidation_events']) for r in panel]);features=[];valid=[];last={}
    binned,_=np.histogram(event_times,bins=np.arange(len(y)+1))
    require(np.array_equal(y,binned),'Event timestamps and hourly count panel do not reconcile')
    for i,r in enumerate(panel):
        key=stamp(r['hour_utc']);values=[];ok=True
        for feed in ['ETH/USD','BTC/USD']:
            v=price[feed].get(key);old=last.get(feed)
            if v is None or old is None or v[1] or old[1]:ok=False;values.extend([0,0])
            else:
                ret=math.log(v[0]/old[0]);values.extend([abs(ret),max(-ret,0)])
            last[feed]=v
        h=int(r['hour_utc'][11:13]);values.extend([math.sin(2*math.pi*h/24),math.cos(2*math.pi*h/24)])
        features.append(values);valid.append(ok)
    features=np.array(features);valid=np.array(valid);train=(np.arange(len(y))<split)&valid;test=(np.arange(len(y))>=split)&valid
    require(train.sum()>100 and test.sum()>20,'Insufficient price-aligned training/test rows')
    center=features[train].mean(axis=0);scale=features[train].std(axis=0);scale[scale==0]=1
    X=np.column_stack([np.ones(len(y)),(features-center)/scale]);fit,_=glm(X[train],y[train]);mu=poisson_predict(X,fit.x);base=np.mean(y[train])
    require(fit.success,f'Poisson optimizer did not converge: {fit.message}')
    write_csv(out/'hourly_predictions.csv',[dict(hour_utc=r['hour_utc'],observed=int(y[i]),prediction=float(mu[i]) if valid[i] else None,valid_prices=bool(valid[i]),sample='train' if i<split else 'test') for i,r in enumerate(panel)])
    # Point-process Poisson comparison uses full continuous observation interval.
    rate=np.sum(event_times<split)/split;ntest=np.sum(event_times>=split);point_ll=ntest*math.log(rate)-rate*(T-split)
    require(best is not None,'No Hawkes candidate converged; see optimizer diagnostics')
    return summary('ready_scoped','Chronological Poisson controls and univariate exponential Hawkes baseline',
      ['Hawkes uses grouped block timestamps with no artificial jitter; continuous-time likelihood is coarsened at block resolution',
       'Hawkes is univariate without price covariates: branching ratio does not establish causal self-excitation',
       'Price controls are contemporaneous hourly returns: explanatory baseline, not an hour-ahead forecast',
       'No Hawkes residual time-rescaling test or multivariate contagion claim; inspect held-out likelihood before interpreting'],
       protocol=proto,train_end_utc=iso(start+split*3600),events=len(times),hours=T,hawkes=best,
       hawkes_minus_constant_poisson_test_loglik=best['test_loglik']-point_ll,
       poisson=dict(converged=bool(fit.success),coefficients=fit.x.tolist(),feature_names=['intercept','abs_ETH_return','negative_ETH_return','abs_BTC_return','negative_BTC_return','hour_sin','hour_cos'],
          training_center=center,training_scale=scale,test_deviance=poisson_deviance(y[test],mu[test]),constant_test_deviance=poisson_deviance(y[test],np.full(test.sum(),base)),excluded_price_rows=int((~valid).sum())))
