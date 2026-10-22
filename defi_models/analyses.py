import csv,json,math
from collections import defaultdict,Counter
import numpy as np
from scipy.spatial import cKDTree
from .core import rows,write_csv,stamp,iso,require,concentration,summary,shock_grid
from .statistics import breakpoint,glm,poisson_deviance,hawkes_fit,poisson_predict

def temporal_positive(record,window,cutoff):
    available=stamp(record['label_available_at']);borrow=float(record['borrow_stamp'])
    require(math.isfinite(borrow) and available>=borrow,'Recursive label precedes its borrow')
    return int(record['window_hours'])==window and available<=cutoff

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

def rq2(data,out,cfg):
    events=data.read('liquidations_model_table.csv');groups=defaultdict(lambda:defaultdict(float));coverage=Counter()
    for r in events:
        proto=r['protocol'];year=r['timestamp_utc'][:4];priced=bool(r['reported_event_amount_market_usd'])
        if priced:
            require(math.isfinite(float(r['reported_event_amount_market_usd'])) and float(r['reported_event_amount_market_usd'])>=0,'Invalid liquidation valuation')
            age=float(r['price_age_seconds']);limit=7200 if r['debt_token']=='0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2' else 90000
            require(math.isfinite(age) and 0<=age<=limit and r['valuation_status']=='market_price_last_known','Priced liquidation has stale/future/unverified valuation')
        coverage[proto,'events']+=1;coverage[proto,'priced']+=priced
        for period in ('all',year):
            for dim,key in [('borrower',r['borrower']),('debt_token',r['debt_token']),('collateral_token',r['collateral_token'])]:
                # Unknown identities are an explicit missing bucket, not silently dropped.
                groups[proto,period,dim,'event_count'][key or 'UNKNOWN']+=1
                if priced:groups[proto,period,dim,'reported_amount_market_usd_priced_subset'][key or 'UNKNOWN']+=float(r['reported_event_amount_market_usd'])
    metrics=[];top=[]
    for (proto,period,dim,measure),weights in sorted(groups.items()):
        metrics.append(dict(protocol=proto,period=period,dimension=dim,measure=measure,**concentration(weights.values())))
        total=sum(weights.values())
        for rank,(entity,v) in enumerate(sorted(weights.items(),key=lambda x:x[1],reverse=True)[:20],1):
            top.append(dict(protocol=proto,period=period,dimension=dim,measure=measure,rank=rank,entity=entity,value=v,share=v/total if total else None))
    write_csv(out/'concentration.csv',metrics);write_csv(out/'top_entities.csv',top)
    cov=[dict(protocol=p,events=coverage[p,'events'],priced_events=coverage[p,'priced'],priced_fraction=coverage[p,'priced']/coverage[p,'events']) for p in sorted({r['protocol'] for r in events})]
    write_csv(out/'valuation_coverage.csv',cov)
    return summary('ready_scoped','HHI, Gini and top shares by protocol and year',
      ['USD measures use priced subset, not full population','Comet basePaidOut is not equivalent to Aave repaid debt; protocols are never pooled',
       'Event counts count liquidation logs, not unique loans'],coverage=cov)

def rq3(data,out,cfg):
    p,scope=data.snapshot();cutoff=data.snapshot_time(scope['block']);window=cfg['recursive_window_hours']
    positive=set();evidence=Counter();mode=cfg['recursive_label']
    if mode=='temporal':
        for r in rows(data.path('recursive_candidates_full_history.csv')):
            if temporal_positive(r,window,cutoff):
                # Future whole-window right censoring is irrelevant once positive evidence is observed.
                positive.add(r['account']);evidence[r['account']]+=1
    else:
        for r in data.read('recursive_receipt_verification.csv'):
            if r['status'].startswith('verified') and int(r['block'])<=scope['block']:positive.add(r['account']);evidence[r['account']]+=1
    accounts=p.accounts;treated=np.array([a in positive for a in accounts]);hf,debt=p.stress();stressed,_=p.stress(.2,.2)
    require(np.any(treated) and np.any(~treated),'No treated/control overlap at snapshot; change label mode or snapshot')
    denom=p.c.sum(axis=1);eth_share=np.divide(p.c[:,p.eth].sum(axis=1),denom,out=np.zeros_like(denom),where=denom>0)
    btc_share=np.divide(p.c[:,p.btc].sum(axis=1),denom,out=np.zeros_like(denom),where=denom>0)
    feature=np.column_stack([np.log1p(debt),np.minimum(hf,10),eth_share,btc_share]);sd=feature.std(axis=0);sd[sd==0]=1
    Z=(feature-feature.mean(axis=0))/sd
    ti=np.flatnonzero(treated);ci=np.flatnonzero(~treated);tree=cKDTree(Z[ci]);k=min(30,len(ci))
    distances,neighbors=tree.query(Z[ti],k=k)
    if k==1:distances=distances[:,None];neighbors=neighbors[:,None]
    # Deterministic greedy matching without replacement, lowest-distance treated first.
    used=set();pairs=[]
    for pos in np.argsort(distances[:,0],kind='stable'):
        for distance,neighbor in zip(distances[pos],neighbors[pos]):
            control=int(ci[int(neighbor)])
            if distance>cfg['match_caliper']:break
            if control not in used:used.add(control);pairs.append((int(ti[pos]),control,float(distance)));break
    require(len(pairs)>=2,'Fewer than two matched pairs; inspect overlap/caliper, do not claim effect')
    future=Counter();horizon=cutoff+cfg['outcome_days']*86400
    bounds=json.loads((data.run/'block_range.json').read_text(encoding='utf8'))
    require(horizon<=stamp(bounds['end_exclusive_utc']),'Outcome horizon is right-censored by data end')
    for r in data.read('liquidations_model_table.csv'):
        if r['protocol']=='aave_v3' and scope['block']<int(r['block']) and stamp(r['timestamp_utc'])<=horizon:future[r['borrower']]+=1
    y=np.array([future[a]>0 for a in accounts],int);result=[]
    for pair,(i,j,distance) in enumerate(pairs,1):
        result.append(dict(pair=pair,treated=accounts[i],control=accounts[j],distance=distance,treated_hf=hf[i],control_hf=hf[j],
            treated_liquidated=int(y[i]),control_liquidated=int(y[j]),treated_stress_eligible=int(stressed[i]<1),control_stress_eligible=int(stressed[j]<1)))
    write_csv(out/'matched_pairs.csv',result)
    balance=[];ii=np.array([i for i,j,d in pairs]);jj=np.array([j for i,j,d in pairs])
    for k,name in enumerate(['log1p_debt','HF_capped_10','ETH_collateral_share','BTC_collateral_share']):
        denom=math.sqrt((feature[ii,k].var()+feature[jj,k].var())/2)
        balance.append(dict(feature=name,treated_mean=feature[ii,k].mean(),control_mean=feature[jj,k].mean(),standardized_mean_difference=(feature[ii,k].mean()-feature[jj,k].mean())/denom if denom>0 else None))
    write_csv(out/'matching_balance.csv',balance)
    diff=y[ii]-y[jj];rng=np.random.default_rng(cfg['seed']);boot=[rng.choice(diff,len(diff),replace=True).mean() for _ in range(cfg['bootstrap_repetitions'])]
    indices=np.ravel(np.column_stack([ii,jj]));X=np.column_stack([np.ones(len(indices)),treated[indices].astype(float),Z[indices]])
    regression={'status':'not_identified_no_outcome_variation'}
    if len(np.unique(y[indices]))==2:
        fit,mu=glm(X,y[indices],family='logistic',ridge=1e-3)
        regression=dict(status='penalized_association_only' if fit.success else 'fit_failed_do_not_interpret',converged=bool(fit.success),message=str(fit.message),coefficients=fit.x.tolist(),coefficient_names=['intercept','treated','log1p_debt_z','HF_z','ETH_share_z','BTC_share_z'],ridge=.001)
    return summary('exploratory','Matched observational comparison using labels available before snapshot',
      ['No-observed-motif controls are not proven unlevered','Temporal labels are candidates; verified positives are a small selected sample',
       'Conditional associations and paired bootstrap are not causal identification; no population extrapolation',
       'Bootstrap holds matching fixed; balance and unmatched treated must be reviewed'],
       label_mode=mode,cutoff_utc=iso(cutoff),outcome_end_utc=iso(horizon),treated_in_snapshot=int(treated.sum()),matched_pairs=len(pairs),
       unmatched_treated=int(treated.sum())-len(pairs),liquidation_risk_difference=diff.mean(),paired_bootstrap_95=np.quantile(boot,[.025,.975]),
       stress_eligibility_difference=np.mean((stressed[ii]<1).astype(int)-(stressed[jj]<1).astype(int)),regression=regression)

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

def rq5(data,out,cfg):
    ps=data.read('exposures_valued_sample.csv');blocks={r['block'] for r in ps};require(len(blocks)==1,'Exposure network must use synchronized block')
    edges=[];debts=defaultdict(lambda:defaultdict(float));collateral=defaultdict(lambda:defaultdict(float));unknown=0;seen=set()
    for r in ps:
        key=tuple(r[k] for k in ['protocol','account','market_id','asset','kind'])
        require(key not in seen,'Duplicate exposure would double-count network weight');seen.add(key)
        if r['priced']!='True':unknown+=1;continue
        value=float(r['value_usd']);kind=r['kind'];protocol=r['protocol'];account=r['account']
        require(math.isfinite(value) and value>=0,'Invalid valued exposure')
        edges.append(dict(wallet=account,protocol=protocol,market=r['market_id'],asset=r['asset'],kind=kind,value_usd=value,block=r['block'],causal_claim=False))
        if kind=='debt':debts[account][protocol]+=value
        if kind=='collateral':collateral[account][protocol]+=value
    write_csv(out/'valued_edges.csv',edges)
    require(edges,'No priced exposure available; cannot interpret empty network as no contagion')
    protocols=sorted({r['protocol'] for r in ps});overlap=[]
    for a in protocols:
        for b in protocols:
            if a>=b:continue
            shared=[w for w,d in debts.items() if d.get(a,0)>0 and d.get(b,0)>0]
            overlap.append(dict(protocol_a=a,protocol_b=b,shared_debt_wallets=len(shared),minimum_shared_debt_usd=sum(min(debts[w][a],debts[w][b]) for w in shared),edge_type='common_wallet_overlap_not_interprotocol_claim'))
    write_csv(out/'protocol_overlap.csv',overlap)
    # Accounting sensitivity: a protocol shock marks sampled borrowers distressed,
    # then measures their other sampled debts. No invented default propagation rates.
    scenarios=[]
    for origin in protocols:
        wallets={w for w,d in debts.items() if d.get(origin,0)>0}
        for target in protocols:
            if origin==target:continue
            scenarios.append(dict(origin=origin,target=target,affected_common_wallets=sum(debts[w].get(target,0)>0 for w in wallets),
              coexposed_debt_usd=sum(debts[w].get(target,0) for w in wallets),interpretation='upper-bound shared-wallet exposure screen; not realized losses'))
    write_csv(out/'common_wallet_sensitivity.csv',scenarios)
    return summary('exploratory','Sampled multilayer exposure network and common-wallet exposure sensitivity',
      ['Activity-selected sample, not full-market network','Co-exposure is not a direct protocol claim or causal contagion channel',
       'No invented recovery rate, default rule or contagion coefficient; propagation estimation requires additional identification'],
       block=next(iter(blocks)),valued_edges=len(edges),unpriced_rows=unknown,wallets=len({r['account'] for r in ps}),protocols=protocols)
