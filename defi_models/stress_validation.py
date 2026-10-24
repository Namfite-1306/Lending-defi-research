"""Evidence and validation gates for objectives 4/5. Never changes frozen inputs.

Run: python -m defi_models.stress_validation --run ... --out ...
"""
import argparse
import csv
import json
import math
from collections import defaultdict,Counter
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from .core import Data,DEFAULTS,concentration,write_csv,write_json,sha


def priced(row,max_age):
    try:
        amount=float(row['reported_event_amount_market_usd']);age=float(row['price_age_seconds'])
        return math.isfinite(amount) and amount>0 and math.isfinite(age) and 0<=age<=max_age
    except (ValueError,KeyError,TypeError):return False


def temporal_concentration(events,max_price_age=3600):
    groups=defaultdict(list)
    for r in events:
        dt=datetime.fromisoformat(r['timestamp_utc']);quarter=f'{dt.year}-Q{(dt.month-1)//3+1}'
        for frequency,period in [('month',dt.strftime('%Y-%m')),('quarter',quarter)]:groups[r['protocol'],frequency,period].append(r)
    output=[]
    for (protocol,frequency,period),rs in sorted(groups.items()):
        good=[r for r in rs if priced(r,max_price_age)]
        for entity in ['borrower','collateral_token']:
            count=Counter(r[entity] for r in good);usd=defaultdict(float)
            for r in good:usd[r[entity]]+=float(r['reported_event_amount_market_usd'])
            all_counts=Counter(r[entity] for r in rs)
            for metric,weights in [('count',count),('usd',usd),('count_all',all_counts)]:
                output.append(dict(protocol=protocol,frequency=frequency,period=period,entity=entity,metric=metric,
                  all_events=len(rs),priced_events=len(good),event_price_coverage=len(good)/len(rs),max_price_age_seconds=max_price_age,
                  common_sample=metric!='count_all',**concentration(weights.values())))
    return output


class QuoteCurve:
    """Total proceeds at observed size grid. No extrapolation or synthetic peg.

Costs include DEX fees already. Interpolation is an approximation between quotes,
not a replacement for tick-by-tick pool simulation. Only the exact source block
and directed token pair are valid. Outputs are in spot-equivalent input USD.
"""
    def __init__(self,rows):
        keys={(r['pool'],int(r['block']),r['token_in'],r['token_out']) for r in rows}
        if len(keys)!=1:raise ValueError('Mixed pool/block/direction quote curve')
        self.key=next(iter(keys));values=sorted((float(r['input_target_usd']),float(r['cost_vs_spot_including_fee'])) for r in rows)
        if len(values)<3 or len({s for s,c in values})!=len(values):raise ValueError('Insufficient/duplicate quote sizes')
        self.x=np.array([s for s,c in values]);self.y=np.array([s*(1-c) for s,c in values])
        if not np.isfinite(self.y).all() or not np.all(self.x>0) or not np.all((self.y>0)&(self.y<=self.x)) or not np.all(np.diff(self.y)>0):raise ValueError('Invalid quote curve')
        self.errors=[]
        for j in range(1,len(self.x)-1):
            mask=np.arange(len(self.x))!=j
            estimate=float(np.interp(self.x[j],self.x[mask],self.y[mask]))
            self.errors.append(abs(estimate-self.y[j])/self.x[j]*10000)
        self.interpolation_passed=max(self.errors)<=10
    def proceeds(self,size,block,token_in,token_out):
        if (block,token_in,token_out)!=self.key[1:]:raise ValueError('Quote state/direction mismatch')
        if not math.isfinite(size) or size<self.x[0] or size>self.x[-1]:raise ValueError('Outside observed quote range; collect new quotes')
        if not np.any(self.x==size) and not self.interpolation_passed:raise ValueError('Interpolation error exceeds 10 bps; collect denser quotes')
        return float(np.interp(size,self.x,self.y))


def quote_diagnostics(rows):
    groups=defaultdict(list)
    for r in rows:
        if r.get('bounded_curve_usable')=='True':groups[r['pool'],r['block'],r['token_in'],r['token_out']].append(r)
    output=[];curves=[]
    for key,rs in sorted(groups.items()):
        try:curve=QuoteCurve(rs)
        except ValueError:continue
        # Leave interior knots out; bracketing points only, never extrapolate.
        errors=[]
        for j in range(1,len(curve.x)-1):
            mask=np.arange(len(curve.x))!=j
            estimated=float(np.interp(curve.x[j],curve.x[mask],curve.y[mask]));errors.append(abs(estimated-curve.y[j])/curve.x[j]*10000)
        curves.extend(rs)
        output.append(dict(pool=key[0],block=int(key[1]),token_in=key[2],token_out=key[3],quotes=len(rs),
          min_input_usd=float(curve.x[0]),max_input_usd=float(curve.x[-1]),
          interior_leave_one_out_mae_bps=float(np.mean(errors)),interior_leave_one_out_max_bps=max(errors),
          exact_at_knots=True,extrapolation_allowed=False,fee_included=True,interpolation_tolerance_bps=10,
          interpolation_gate_passed=curve.interpolation_passed,
          validation_scope='held-out quote sizes within source pool/block, not unseen-event cascade backtest'))
    return output,curves


def stress_windows(events,count=5):
    """Rank nonoverlapping calendar UTC days ex post; diagnostic selection only."""
    groups=defaultdict(list)
    for r in events:
        if r['protocol']=='aave_v3':groups[r['timestamp_utc'][:10]].append(r)
    top=sorted(groups.items(),key=lambda item:(-len(item[1]),item[0]))[:count]
    output=[]
    for rank,(day,rs) in enumerate(top,1):
        output.append(dict(rank=rank,date=day,protocol='aave_v3',observed_events=len(rs),borrowers=len({r['borrower'] for r in rs}),
          first_event_block=min(int(r['block']) for r in rs),last_event_block=max(int(r['block']) for r in rs),
          selection='ex_post_top_event_days_not_pre_registered',
          observed_priced_usd=sum(float(r['reported_event_amount_market_usd']) for r in rs if priced(r,3600)),
          historical_position_replay_status='pending_pre_window_full_snapshot_and_price_oracle_path'))
    return output


def build(run,out,max_price_age=3600,extra_quotes=None):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);data=Data(run,DEFAULTS)
    events=data.read('liquidations_model_table.csv');quotes=data.read('v3_exact_impact_quotes.csv');replays=data.read('v3_swap_replay_validation.csv')
    extra=None
    if extra_quotes:
        with Path(extra_quotes).open(encoding='utf-8-sig',newline='') as f:added=list(csv.DictReader(f))
        quotes+=added;extra={'file':str(Path(extra_quotes).resolve()),'sha256':sha(extra_quotes),'rows':len(added),'frozen_dataset_input':False}
    table=temporal_concentration(events,max_price_age);diagnostics,curves=quote_diagnostics(quotes);windows=stress_windows(events)
    write_csv(out/'concentration_by_period.csv',table);write_csv(out/'quote_curve_validation.csv',diagnostics)
    write_csv(out/'bounded_quote_curves.csv',curves,fields=sorted({k for r in curves for k in r}));write_csv(out/'backtest_event_plan.csv',windows)
    eligible=[r for r in replays if r.get('eligible')=='True'];matched=[r for r in eligible if r.get('exact_replay_match')=='True']
    evidence={'generated_at':datetime.now(timezone.utc).isoformat(),'data_run':str(Path(run).resolve()),
      'input_hashes':{str(p.relative_to(run)):sha(p) for p in sorted(data.used)},
      'concentration':{'status':'completed_scoped','rows':len(table),'max_price_age_seconds':max_price_age,
        'note':'Count/USD use identical priced events. Coverage is by events, not by dollars. Protocol USD meanings differ.'},
      'dex':{'status':'quote_grids_scoped_interpolation_gated','source_quotes':len(quotes),'usable_curves':len(diagnostics),
        'interpolation_passed_curves':sum(r['interpolation_gate_passed'] for r in diagnostics),
        'source_blocks':len({r['block'] for r in diagnostics}),'swap_cases':len(replays),'eligible_replays':len(eligible),'exact_matches':len(matched),
        'excluded_replays':len(replays)-len(eligible),'match_rate_eligible':len(matched)/len(eligible) if eligible else None,
        'note':'Existing archived Quoter/swap evidence; not a new network replay. Curves cannot be reused at other blocks or extrapolated.'},
      'cascade_backtest':{'status':'not_validated','event_days_selected':len(windows),'missing':[
        'pre-window full borrower snapshots for selected event dates',
        'oracle update paths and time-matched DEX quotes through each window',
        'revision-specific liquidation pair rules and execution replay',
        'held-out event tests and uncertainty intervals'],
        'note':'DEX replay match is not proof of a calibrated end-to-end liquidation cascade.'},
      'scope':'Aave stress focus; concentration reported separately for Aave, Comet USDC, Morpho'}
    evidence['additional_quote_input']=extra
    write_json(out/'evidence.json',evidence)
    return evidence


def pair_study(run,out,risk_params=None):
    from .pair_cascade import pair_cascade
    data=Data(run,DEFAULTS);p,scope=data.snapshot();results=[];trajectories=[]
    risk=None;overrides={}
    if risk_params:
        risk=json.loads(Path(risk_params).read_text(encoding='utf8'))
        if risk['block']!=scope['block'] or risk['pool_revision']!=scope['pool_revision']:raise ValueError('Risk parameters do not match snapshot')
        position_file=Path(run)/DEFAULTS['snapshot']/'positions.csv'
        with position_file.open(encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                mode=r['emode'];token=r['token']
                if mode!='0' and int(risk['emode_collateral_bitmap'][mode])&(1<<risk['reserve_ids'][token]):overrides.setdefault(r['account'],{})[token]=risk['emode_bonus'][mode]
    # Matched scenario controls; oracle delay is in abstract rounds, not seconds.
    for shock in [.1,.2,.3]:
        for impact in [0.,.05]:
            for delay in [0,1,3]:
                cfg=dict(DEFAULTS,max_rounds=30,impact_coefficient=impact,oracle_delay_rounds=delay)
                if risk:cfg.update(bonus_by_token=risk['bonus_by_token'],protocol_fee_by_token=risk['protocol_fee_by_token'],bonus_by_account_token=overrides)
                result,history,actions=pair_cascade(p,shock,cfg)
                result.update(impact_coefficient=impact,snapshot_block=scope['block'],cohort_wallets=len(p.accounts),bonus_source='historical_reserve_and_emode' if risk else 'uniform_assumption')
                results.append(result)
                trajectories.extend(dict(shock=shock,impact_coefficient=impact,oracle_delay_rounds=delay,**r) for r in history)
    write_csv(Path(out)/'pair_scenarios.csv',results);write_csv(Path(out)/'pair_rounds.csv',trajectories)
    evidence_path=Path(out)/'evidence.json';evidence=json.loads(evidence_path.read_text(encoding='utf8'))
    evidence['pair_engine']={'status':'experimental_completed','scenarios':len(results),'snapshot_block':scope['block'],
      'wallets':len(p.accounts),'historically_calibrated':False,'supported_protocol_revision':6,
      'note':'Revision-6 selected-debt close-factor sensitivity, assumed uniform bonus/depth, no full transaction equivalence; delays are rounds, not seconds.'}
    if risk:
        evidence['pair_engine']['risk_parameter_source']={'file':str(Path(risk_params).resolve()),'sha256':sha(risk_params),'block':risk['block']}
        evidence['pair_engine']['note']='Historical reserve/E-mode bonuses and protocol liquidation fees; assumed liquidity/ordering/delay; not exact EVM or calibrated cascade.'
    write_json(evidence_path,evidence)
    return results


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--max-price-age',type=int,default=3600);p.add_argument('--pair-study',action='store_true');p.add_argument('--extra-quotes',type=Path);p.add_argument('--risk-params',type=Path);args=p.parse_args()
    if args.max_price_age<0:p.error('max-price-age must be nonnegative')
    result=build(args.run,args.out,args.max_price_age,args.extra_quotes)
    if args.pair_study:
        pair_study(args.run,args.out,args.risk_params);result=json.loads((args.out/'evidence.json').read_text(encoding='utf8'))
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
