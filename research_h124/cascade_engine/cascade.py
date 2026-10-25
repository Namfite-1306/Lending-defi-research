"""Version-aware economic approximation; never presented as exact EVM replay.

Historical quotes calibrate an impact sensitivity, not an execution guarantee at
another block. Unknown routes are excluded explicitly; no zero-impact fallback.
"""
import json,math
from collections import defaultdict
import numpy as np
from defi_models.core import Portfolio,DEFAULTS
from .v2_common import *

def repay_limit(revision,hf,total_debt,reserve_debt,selected_collateral):
    if not 1<=revision<=11:raise ValueError('Unreviewed revision')
    if revision<=6:return reserve_debt*(1 if hf<=.95 else .5)
    if hf<=.95 or min(reserve_debt,selected_collateral)<2000:return reserve_debt
    return min(reserve_debt,.5*total_debt)

def no_dust_amount(revision,amount,debt,collateral,bonus):
    if revision<=6:return amount
    if amount>=debt-1e-7 or amount*(1+bonus)>=collateral-1e-7:return amount
    # Partial liquidation must leave >=$1,000 in BOTH selected reserves. Reduce
    # the proposal rather than silently violating the close-factor or dust rule.
    return max(0,min(amount,debt-1000,(collateral-1000)/(1+bonus)))

def parameters(folder):
    scope=load(folder/'scope.json',{})
    if not scope.get('full_snapshot_complete'):raise ValueError('Full snapshot required')
    freeze=load(folder/'freeze_manifest.json',{})
    if not freeze or any(digest(folder/name)!=value for name,value in freeze['files'].items()):raise ValueError('Snapshot freeze mismatch')
    reserves=read(folder/'reserve_metadata.csv');positions=read(folder/'positions.csv');cats=load(folder/'emode_categories.json',{})
    bonus={r['token']:float(r['liquidation_bonus_factor'])-1 for r in reserves}
    fee={r['token']:((int(r['configuration_word'])>>152)&65535)/10000 for r in reserves}
    enabled={r['token']:bool((int(r['configuration_word'])>>56)&1) and not bool((int(r['configuration_word'])>>60)&1) for r in reserves}
    by_account=defaultdict(dict);meta={r['token']:r for r in reserves}
    for r in positions:
        mode=str(r['emode']);token=r['token'];cat=cats.get(mode)
        if cat and (int(cat['bitmap'])&(1<<int(meta[token]['reserve_id'])) if cat['bitmap'] is not None else int(meta[token]['category'])==int(mode)):
            by_account[r['account']][token]=float(cat['liquidation_bonus_factor'])-1
    return Portfolio(positions,DEFAULTS),{'revision':scope['pool_revision'],'bonus':bonus,'fees':fee,'enabled':enabled,'emode_bonus':dict(by_account),'block':scope['block']}

def simulate(p,params,path,impact_by_token,feedback=True,capacity=1500,gas_usd=20,delay_steps=0):
    if not path or capacity<1 or gas_usd<0 or delay_steps<0:raise ValueError('Invalid simulation controls')
    c=p.c.copy();d=p.d.copy();repay=p.repay.copy();n,m=c.shape;impact=np.zeros(m);cumulative=np.zeros(m);past=[impact.copy()]
    bonus=np.array([[params['emode_bonus'].get(a,{}).get(token,params['bonus'][token]) for token in p.tokens] for a in p.accounts])
    fee=np.array([params['fees'][token] for token in p.tokens]);enabled=np.array([params['enabled'][token] for token in p.tokens])
    coef=np.array([impact_by_token.get(token,np.nan) for token in p.tokens])
    if 'routes' in params:
        allowed=np.array([[f'{a}|{b}' in params['routes'] for b in p.tokens] for a in p.tokens])&enabled[:,None]&enabled[None,:]
    else:allowed=(np.isfinite(coef)&enabled)[:,None]&enabled[None,:]
    route=allowed.any(axis=1)
    original_eligible=None;affected=set();newly=set();actions=[];rounds=[];deficits=0.
    for step,exogenous in enumerate(path):
        ex=np.where(p.eth,exogenous['ETH'],np.where(p.btc,exogenous['BTC'],1.))
        if np.any(ex<=0) or not np.isfinite(ex).all():raise ValueError('Invalid exogenous price path')
        observed=past[max(0,len(past)-1-delay_steps)] if feedback else np.zeros(m)
        f=ex*(1-observed);cv=c*f;dv=d*f;rv=repay*f;debt=dv.sum(axis=1)
        hf=np.divide((cv*p.lt).sum(axis=1),debt,out=np.full(n,np.inf),where=debt>1e-8);eligible=(hf<1)&(rv.sum(axis=1)>1e-6)
        if original_eligible is None:original_eligible=set(np.flatnonzero(eligible))
        can_repay=(rv>1e-8).astype(int)@allowed.T>0
        choice=np.where(route[None,:]&can_repay,cv,-1).argmax(axis=1);ix=np.arange(n)
        j=np.where(allowed[choice],rv,-1).argmax(axis=1)
        has_route=allowed[choice,j]&(rv[ix,j]>1e-8)&(cv[ix,choice]>1e-8);proposed=[]
        for i in np.flatnonzero(eligible&has_route&enabled[j]):
            k=choice[i];debt_token=j[i];b=bonus[i,k]
            maximum=repay_limit(params['revision'],hf[i],debt[i],rv[i,debt_token],cv[i,k])
            amount=min(maximum,cv[i,k]/(1+b));amount=no_dust_amount(params['revision'],amount,rv[i,debt_token],cv[i,k],b)
            if amount>1e-6:proposed.append((i,k,debt_token,amount,b))
        # Ordering is an explicit assumption: most distressed first, stable account tie break.
        proposed.sort(key=lambda z:(hf[z[0]],p.accounts[z[0]]));executed=0;repaid=0.;unprofitable=0
        for i,k,jj,amount,b in proposed:
            if executed>=capacity:break
            received=amount*(1+b*(1-fee[k]));sold_reference=received/f[k]*ex[k] if k!=jj else 0.
            key=f'{p.tokens[k]}|{p.tokens[jj]}';coefficient=params.get('pair_impact',{}).get(key,coef[k])
            if k==jj:coefficient=0.
            if not np.isfinite(coefficient):raise ValueError('Missing measured pair impact; no zero-impact fallback')
            next_impact=(impact[k] if k==jj else min(.8,coefficient*math.sqrt((cumulative[k]+sold_reference)/1e6))) if feedback else 0.
            market_cost=amount*ex[jj]*(1-impact[jj])/f[jj]
            execution_fee=params.get('routes',{}).get(key,.0005)
            proceeds=received/f[k]*ex[k]*(1-(impact[k]+next_impact)/2)*(1-execution_fee)
            profit=proceeds-market_cost-gas_usd
            if profit<=0:unprofitable+=1;continue
            fraction=amount/rv[i,jj];seized=amount*(1+b);before_c=c[i,k];before_d=d[i,jj];before_r=repay[i,jj]
            c[i,k]-=seized/f[k];d[i,jj]*=1-fraction;repay[i,jj]*=1-fraction
            if min(c[i,k],d[i,jj],repay[i,jj]) < -1e-5:raise ValueError('Balance conservation failure')
            c[i,k]=max(0,c[i,k]);d[i,jj]=max(0,d[i,jj]);repay[i,jj]=max(0,repay[i,jj])
            writeoff=0.
            if params['revision']>=7 and c[i].sum()<1e-6:
                writeoff=float((repay[i]*f).sum());deficits+=writeoff;d[i]=0;repay[i]=0
            cumulative[k]+=sold_reference;impact[k]=next_impact;executed+=1;repaid+=amount;affected.add(i)
            if i not in original_eligible:newly.add(i)
            actions.append({'step':step,'account':p.accounts[i],'debt_token':p.tokens[jj],'collateral_token':p.tokens[k],
              'repaid_usd':amount,'seized_usd':seized,'received_collateral_usd':received,'protocol_fee_usd':seized-received,
              'profit_usd':profit,'hf_before':hf[i],'bonus':b,'deficit_writeoff_usd':writeoff,
              'collateral_decrement_base_usd':before_c-c[i,k],'risk_debt_decrement_base_usd':before_d-d[i,jj],'repayable_decrement_base_usd':before_r-repay[i,jj]})
        past.append(impact.copy());rounds.append({'step':step,'eligible_wallets':int(eligible.sum()),'unsupported_route_wallets':int((eligible&~has_route).sum()),
          'executed_pairs':executed,'unprofitable':unprofitable,'repaid_usd':repaid,'max_impact':float(impact.max()),'ETH_factor':exogenous['ETH'],'BTC_factor':exogenous['BTC']})
    result={'wallets':n,'steps':len(path),'repaid_usd':sum(a['repaid_usd'] for a in actions),'executed_pairs':len(actions),'liquidated_wallets':len(affected),
      'newly_eligible_liquidated_wallets':len(newly),'deficit_writeoff_usd':deficits,'feedback':feedback,'historically_calibrated':False,
      'rule_adapter_revision':params['revision'],'gas_usd_assumed':gas_usd,'capacity_pairs_per_step_assumed':capacity,
      'limitations':['Economic float approximation, not exact EVM transaction replay','Close-factor/dust/fee core rules only; grace periods/sentinel and full token transfer behavior not replayed',
        'Fitted square-root impact can extrapolate: sensitivity only, not executable quote','Measured direct-route fee where available; gas and ordering are assumptions; unsupported debt/collateral pairs excluded',
        'ETH/BTC family factors approximate derivatives; other price factors held fixed','End-to-end held-out historical calibration not yet passed']}
    return result,rounds,actions

def calibrate():
    quotes_path=OUT/'cascade/quote_path.csv'
    if not quotes_path.exists():return {}
    if not load(OUT/'cascade/quote_collection.json',{}).get('complete'):return {}
    quotes=read(quotes_path);dates=sorted({r['event_date'] for r in quotes});train=dates[:max(1,len(dates)-2)];test=dates[len(train):]
    def directed_move(r):
        factor=1+float(r['price_move_token1_per_token0'])
        if factor<=0:raise ValueError('Invalid quote price factor')
        return max(0,1-factor if r['token_in'].lower()<r['token_out'].lower() else 1-1/factor)
    groups=defaultdict(list);pair_groups=defaultdict(list);routes={}
    for r in quotes:
        if r['event_date'] not in train or float(r['price_move_token1_per_token0'])==0:continue
        groups[r['token_in']].append(directed_move(r)/math.sqrt(float(r['input_target_usd'])/1e6))
        key=r['token_in']+'|'+r['token_out'];pair_groups[key].append(directed_move(r)/math.sqrt(float(r['input_target_usd'])/1e6));routes[key]=float(r['fee_pips'])/1e6
    coefficients={token:float(np.median(values)) for token,values in groups.items()}
    pair_coefficients={key:float(np.median(values)) for key,values in pair_groups.items()}
    validation=[]
    for r in quotes:
        key=r['token_in']+'|'+r['token_out']
        if r['event_date'] not in test or key not in pair_coefficients:continue
        actual=directed_move(r);predicted=pair_coefficients[key]*math.sqrt(float(r['input_target_usd'])/1e6)
        validation.append({'event_date':r['event_date'],'pool':r['pool'],'token_in':r['token_in'],'size':r['input_target_usd'],'actual_abs_move':actual,'predicted_abs_move':predicted,'absolute_error_bps':abs(actual-predicted)*10000})
    write(OUT/'cascade/impact_holdout_errors.csv',validation)
    result={'updated_utc':now(),'training_dates':train,'heldout_dates':test,'impact_by_token':coefficients,'impact_by_pair':pair_coefficients,'routes':routes,'heldout_quotes':len(validation),
      'median_heldout_error_bps':float(np.median([r['absolute_error_bps'] for r in validation])) if validation else None,
      'status':'impact_sensitivity_fit_only','limitation':'Quote impact fit is not end-to-end cascade validation; dates selected retrospectively. Move normalized to token-in selling direction.'}
    save(OUT/'cascade/impact_calibration.json',result);return coefficients

_PATH_CACHE={}
def actual_path(item):
    readiness=load(OUT/'h4_data_readiness.json',{})
    prefix=False
    if readiness.get('status')!='completed_scoped':
        readiness=load(OUT/'h4_prefix_data_readiness.json',{});prefix=True
        from defi_models.core import stamp
        if readiness.get('status')!='completed_scoped' or item['stamp']+3601>=stamp(readiness['source']['end_exclusive']):return None
    key=(item['stamp'],readiness.get('header_ledger_sha256'),readiness.get('oracle_updates_sha256'))
    if key in _PATH_CACHE:return _PATH_CACHE[key]
    from .h4_data import block_connection,oracle_rows,asof
    c=block_connection();headers={b:t for b,t in c.execute('SELECT block,stamp FROM headers')};c.close();rows=oracle_rows()
    if prefix:rows=[r for r in rows if int(r['block'])<readiness['first_unverified_block']]
    times=item['stamp']+1+np.arange(13)*300;factors=[]
    for feed in ['ETH/USD','BTC/USD']:
        rs=sorted((r for r in rows if r['feed']==feed),key=lambda r:int(r['block']))
        values,_=asof(times,[headers[int(r['block'])] for r in rs],[float(r['price_usd']) for r in rs])
        update,_=asof(times,[headers[int(r['block'])] for r in rs],[int(r['stamp']) for r in rs])
        if not np.isfinite(values).all() or values[0]<=0 or np.any(times-update>7200):return None
        factors.append(values/values[0])
    result=[{'ETH':float(a),'BTC':float(b)} for a,b in zip(factors[0][1:],factors[1][1:])];_PATH_CACHE[key]=result;return result

def run():
    coefficients=calibrate()
    if not coefficients:return []
    result=[];backtests=[];cal=load(OUT/'cascade/impact_calibration.json',{})
    for item in load(DATA/'cascade_snapshots/quarter_plan.json',[]):
        folder=DATA/'cascade_snapshots'/item['quarter'];scope=load(folder/'scope.json',{})
        if not scope.get('full_snapshot_complete'):continue
        path_actual=actual_path(item)
        identity={'snapshot':digest(folder/'freeze_manifest.json'),'coefficients':coefficients,'pair_coefficients':cal.get('impact_by_pair',{}),'routes':cal.get('routes',{}),'actual_path':path_actual,'engine_sha256':digest(__file__)}
        cache=OUT/'cascade'/item['quarter']/'analysis_identity.json'
        if load(cache)==identity:
            result+=read(cache.parent/'scenarios.csv');backtests+=read(cache.parent/'backtest.csv');continue
        p,params=parameters(folder);local=[];bt=[]
        params['routes']={**cal.get('routes',{}),**{f'{token}|{token}':0. for token in p.tokens}}
        params['pair_impact']=cal.get('impact_by_pair',{})
        for shock in [.1,.2,.3]:
            path=[{'ETH':1-shock,'BTC':1-shock}]*12;pair={}
            for feedback in [False,True]:
                summary,rounds,actions=simulate(p,params,path,coefficients,feedback=feedback);pair[feedback]=summary
                dest=OUT/'cascade'/item['quarter']/f'shock_{shock}_feedback_{feedback}';write(dest/'rounds.csv',rounds);write(dest/'actions.csv',actions);save(dest/'summary.json',summary)
            without=pair[False]['repaid_usd'];withfb=pair[True]['repaid_usd']
            local.append({'event_date':item['quarter'],'shock':shock,'without_feedback_repaid':without,'with_feedback_repaid':withfb,
              'incremental_repaid':withfb-without,'amplification':withfb/without if without else None,'historically_calibrated':False})
        if path_actual:
            start=item['stamp']+1;all_events=[r for r in read(V1_OUT/'h2/episodes.csv') if r['protocol']=='aave_v3' and start<=int(r['stamp'])<start+3600]
            legs={r['episode']:r['token'] for r in read(V1_OUT/'h2/collateral_legs.csv') if r['protocol']=='aave_v3'};accounts=set(p.accounts)
            events=[r for r in all_events if r['borrower'] in accounts and f"{legs.get(r['episode'],'')}|{r['debt_token']}" in params['routes']]
            for feedback in [False,True]:
                summary,rounds,actions=simulate(p,params,path_actual,coefficients,feedback=feedback)
                dest=OUT/'cascade'/item['quarter']/f'actual_path_feedback_{feedback}';write(dest/'rounds.csv',rounds);write(dest/'actions.csv',actions);save(dest/'summary.json',summary)
                valued=[r for r in events if r['debt_usd_upper']!='']
                bt.append({'event_date':item['quarter'],'evaluation':'heldout_date_retrospective_selection' if item['quarter'] in cal.get('heldout_dates',[]) else 'training_date',
                  'feedback':feedback,'observed_all_route_events':len(all_events),'observed_matched_route_events':len(events),'observed_valued_events':len(valued),'observed_valued_debt_usd':sum(float(r['debt_usd_upper']) for r in valued),
                  'predicted_covered_route_actions':summary['executed_pairs'],'predicted_covered_route_repaid_usd':summary['repaid_usd'],
                  'valuation_event_coverage':len(valued)/len(events) if events else None,'route_samples_comparable':True,'end_to_end_validated':False,
                  'absolute_count_error':abs(summary['executed_pairs']-len(events)),
                  'note':'Same pre-event active accounts and measured direct routes; realized oracle path conditions on market feedback already observed, not identified exogenous shocks or a causal forecast.'})
        write(cache.parent/'scenarios.csv',local);write(cache.parent/'backtest.csv',bt);save(cache,identity);result+=local;backtests+=bt
    write(OUT/'cascade/actual_path_backtest.csv',backtests)
    write(OUT/'cascade/scenario_comparison.csv',result);save(OUT/'cascade/readiness.json',{'updated_utc':now(),'scenarios':len(result),'status':'experimental_sensitivity' if result else 'waiting_for_full_pre_event_snapshots',
      'end_to_end_backtest_passed':False,'missing':['full actual-window price-path/execution backtest','complete liquidity routes and grace-period/sentinel adapters','calibrated gas/throughput/ordering','fresh independent event selection']})
    return result
if __name__=='__main__':run()
