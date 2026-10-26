"""Chronological impact calibration and conditional execution diagnostics.

Uses prior event dates only for each fit. Realized oracle paths are conditional
inputs and do not identify exogenous shocks; end-to-end validation stays false.
"""
import math
from collections import defaultdict
import numpy as np
from research_h124.cascade import parameters,simulate
from .common import *

def directed_move(r):
    factor=1+float(r['price_move_token1_per_token0'])
    if factor<=0:raise ValueError('Nonpositive price factor')
    return max(0.,1-factor if r['token_in'].lower()<r['token_out'].lower() else 1-1/factor)

def fit_quotes(quotes,cutoff):
    pair=defaultdict(list);tokens=defaultdict(list);routes={};dates=set()
    for r in quotes:
        if r['event_date']>=cutoff or r['bounded_curve_usable']!='True' or float(r['input_target_usd'])<=0:continue
        move=directed_move(r)
        if move<=0:continue
        value=move/math.sqrt(float(r['input_target_usd'])/1e6);key=r['token_in']+'|'+r['token_out'];fee=float(r['fee_pips'])/1e6
        if key in routes and routes[key]!=fee:raise ValueError('Ambiguous multi-pool fee requires route-level adapter')
        pair[key].append(value);tokens[r['token_in']].append(value);routes[key]=fee;dates.add(r['event_date'])
    return {k:float(np.median(v)) for k,v in tokens.items()},{k:float(np.median(v)) for k,v in pair.items()},routes,sorted(dates)

def run():
    old=ROOT/'results/research_h124_v2_20261024/cascade';snap=ROOT/'data/research_h124_v2_20261024/cascade_snapshots'
    quotes_path=old/'quote_path.csv';quotes=read(quotes_path);source_hash=digest(quotes_path)
    episodes_path=ROOT/'results/research_h124_20261024/h2/episodes.csv';legs_path=episodes_path.parent/'collateral_legs.csv'
    episodes=read(episodes_path);legs=defaultdict(list)
    for r in read(legs_path):legs[r['episode']].append(r['token'])
    outputs=[];quote_errors=[];coverage=[];window_coverage=[];missing_routes=[];identities={str(quotes_path.relative_to(ROOT)):source_hash,str(episodes_path.relative_to(ROOT)):digest(episodes_path),str(legs_path.relative_to(ROOT)):digest(legs_path)}
    save(OUT/'cascade/protocol.json',{'locked_utc':now(),'fit_rule':'impact quotes from strictly earlier event dates only','numeric_diagnostic_gates':{'relative_count_error':.25,'relative_repaid_error':.25,'observed_route_coverage':.8,'valuation_coverage':.95},'date_selection':'retrospective; no new independent holdout','realized_oracle_path_is_conditional':True,'end_to_end_validated':False})
    for item in load(snap/'quarter_plan.json'):
        date=item['quarter'];folder=snap/date;scope=load(folder/'scope.json') if (folder/'scope.json').exists() else {}
        if date>'2026-03-31':coverage.append({'date':date,'status':'outside_primary_scope_not_reintroduced'});continue
        if not scope.get('full_snapshot_complete'):coverage.append({'date':date,'status':'incomplete_pre_event_snapshot','scanned':scope.get('wallets_scanned'),'required':item['historical_borrowers']});continue
        available_routes={r['token_in']+'|'+r['token_out'] for r in quotes if r['event_date']==date and r['offset_minutes']=='0' and r['bounded_curve_usable']=='True'}
        cohort={r['account'] for r in read(folder/'positions.csv')};start=item['stamp']+1
        for hours in [1,6,24]:
            observed_window=[r for r in episodes if r['protocol']=='aave_v3' and start<=int(r['stamp'])<start+hours*3600]
            supported=[r for r in observed_window if len(legs[r['episode']])==1 and (legs[r['episode']][0]+'|'+r['debt_token'] in available_routes or legs[r['episode']][0]==r['debt_token'])]
            matched_window=[r for r in supported if r['borrower'] in cohort]
            window_coverage.append({'event_date':date,'hours':hours,'all_events':len(observed_window),'supported_route_events':len(supported),'pre_snapshot_matched_events':len(matched_window),'matched_coverage':len(matched_window)/len(observed_window) if observed_window else None,'role':'coverage planning only, not an extended-window model backtest'})
            if hours==24:
                absent=defaultdict(int)
                for r in observed_window:
                    if len(legs[r['episode']])!=1:continue
                    key=legs[r['episode']][0]+'|'+r['debt_token']
                    if key not in available_routes and legs[r['episode']][0]!=r['debt_token']:absent[key]+=1
                missing_routes += [{'event_date':date,'collateral_to_debt_pair':key,'events_24h':count} for key,count in sorted(absent.items(),key=lambda x:-x[1])]
        token_coeff,pair_coeff,routes,train_dates=fit_quotes(quotes,date)
        if not token_coeff:coverage.append({'date':date,'status':'no_earlier_calibration_dates'});continue
        identity=old/date/'analysis_identity.json';path=load(identity).get('actual_path') if identity.exists() else None
        if not path:coverage.append({'date':date,'status':'no_verified_oracle_path'});continue
        identities[str(identity.relative_to(ROOT))]=digest(identity)
        for r in quotes:
            key=r['token_in']+'|'+r['token_out']
            if r['event_date']!=date or key not in pair_coeff:continue
            actual=directed_move(r);pred=pair_coeff[key]*math.sqrt(float(r['input_target_usd'])/1e6)
            quote_errors.append({'event_date':date,'train_dates':','.join(train_dates),'pair':key,'input_target_usd':r['input_target_usd'],'offset_minutes':r['offset_minutes'],'absolute_error_bps':abs(actual-pred)*10000})
        p,params=parameters(folder);params['pair_impact']=pair_coeff;params['routes']={**routes,**{f'{t}|{t}':0. for t in p.tokens}}
        freeze=load(folder/'freeze_manifest.json')
        for name,h in freeze['files'].items():identities[str((folder/name).relative_to(ROOT))]=h
        accounts=set(p.accounts);start=item['stamp']+1
        observed=[r for r in episodes if r['protocol']=='aave_v3' and start<=int(r['stamp'])<start+3600]
        matched=[r for r in observed if r['borrower'] in accounts and len(legs[r['episode']])==1 and legs[r['episode']][0]+'|'+r['debt_token'] in params['routes']]
        valued=[r for r in matched if r['debt_usd_upper']!=''];observed_usd=sum(float(r['debt_usd_upper']) for r in valued)
        for feedback in [False,True]:
            result,rounds,actions=simulate(p,params,path,token_coeff,feedback=feedback)
            count_error=abs(result['executed_pairs']-len(matched))/len(matched) if matched else None
            value_error=abs(result['repaid_usd']-observed_usd)/observed_usd if observed_usd else None
            route_cov=len(matched)/len(observed) if observed else None;valuation=len(valued)/len(matched) if matched else None
            passed=all(v is not None for v in [count_error,value_error,route_cov,valuation]) and count_error<=.25 and value_error<=.25 and route_cov>=.8 and valuation>=.95
            outputs.append({'event_date':date,'training_dates':','.join(train_dates),'feedback':feedback,'observed_all_events':len(observed),'observed_matched_events':len(matched),'observed_matched_oracle_debt_usd':observed_usd,
              'predicted_actions':result['executed_pairs'],'predicted_repaid_usd':result['repaid_usd'],'relative_count_error':count_error,'relative_repaid_error':value_error,'observed_route_coverage':route_cov,'valuation_coverage':valuation,'numeric_diagnostic_gates_passed':passed,'end_to_end_validated':False})
            dest=OUT/'cascade'/date/str(feedback);save(dest/'summary.json',result);write(dest/'rounds.csv',rounds);write(dest/'actions.csv',actions)
        coverage.append({'date':date,'status':'chronological_conditional_diagnostic_completed','training_dates':','.join(train_dates)})
        print('CASCADE FORWARD',date,'training',train_dates,flush=True)
        write(OUT/'cascade/forward_backtest.csv',outputs);write(OUT/'cascade/quote_errors.csv',quote_errors);write(OUT/'cascade/coverage.csv',coverage)
    write(OUT/'cascade/coverage.csv',coverage)
    write(OUT/'cascade/window_coverage.csv',window_coverage);write(OUT/'cascade/missing_routes.csv',missing_routes)
    if any(digest(ROOT/p)!=h for p,h in identities.items()):raise ValueError('Frozen cascade source changed')
    result={'updated_utc':now(),'status':'completed_chronological_diagnostics','backtest_rows':len(outputs),'quote_rows':len(quote_errors),'median_quote_error_bps':float(np.median([r['absolute_error_bps'] for r in quote_errors])) if quote_errors else None,'source_hashes':identities,'end_to_end_validated':False,
      'limitations':['Chronological quote fits remove future calibration dates but event selection was retrospective','Realized oracle paths may contain market feedback and are conditional inputs, not identified exogenous shocks','Direct-route sample does not cover the full lending market','2026-02-05 snapshot incomplete; no new archive source available; excluded quarters not restored']}
    save(OUT/'cascade/summary.json',result);return result

if __name__=='__main__':run()
