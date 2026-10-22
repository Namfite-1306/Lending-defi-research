"""Independent arithmetic / integrity audit of an existing pilot run."""
import argparse
import csv
import hashlib
import json
import sqlite3
from collections import Counter,defaultdict
from contextlib import closing
from datetime import datetime,timezone,timedelta
from decimal import Decimal,InvalidOperation,getcontext
from pathlib import Path
from .pipeline import ROOT,CONTRACTS,ts
from .evm import addr,words,uint,calldata,parse_events,decode_event
from .rpc import Rpc,RpcError

getcontext().prec=70
D=Decimal

def read(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def cached(method,params):
    key=json.dumps([method,params],sort_keys=True,separators=(',',':')).encode()
    name=hashlib.sha256(key).hexdigest()+'.json'
    base=ROOT/'data/rpc_cache'
    # Offline arithmetic can refer to a pilot collected before transport_v2.
    # This compatibility read is never used by fresh --live probes.
    for folder in (base/'transport_v2',base):
        path=folder/name
        if path.exists():return json.loads(path.read_text(encoding='utf8'))
    raise FileNotFoundError('Oracle evidence missing from collection cache; regenerate the valuation inputs')

def live(method,params,rpc=None):
    client=rpc if rpc is not None else Rpc(ROOT/'data/rpc_cache')
    # Audit evidence must come from a new request, never from collection cache.
    return client.one(method,params,cache=False)


def live_checks(rpc,manifest,scope,events,validations,specs):
    """Three fresh-data checks; keep unavailable probes as explicit failures."""
    checks=[]
    def collect(name,probe):
        try:
            passed,detail=probe()
            checks.append({'check':name,'passed':bool(passed),'detail':detail})
        except RpcError as exc:
            checks.append({'check':name,'passed':False,'detail':{
                'status':'rpc_unavailable','error':str(exc),'endpoint_failures':exc.failures}})
        except (ValueError,KeyError,TypeError,IndexError,InvalidOperation) as exc:
            checks.append({'check':name,'passed':False,'detail':{
                'status':'invalid_response_or_input','error':str(exc)}})

    try:
        chain=int(live('eth_chainId',[],rpc),16)
        if chain!=1:raise ValueError(f'Expected Ethereum mainnet chain ID 1; received {chain}')
    except (RpcError,ValueError) as exc:
        for name in ('fresh_rpc_receipts','fresh_rpc_window_boundaries','fresh_rpc_snapshot_hf'):
            checks.append({'check':name,'passed':False,'detail':{'status':'chain_check_failed','error':str(exc)}})
        return checks

    def receipts():
        probes=[];skipped=[]
        units={'aave_v3':'LiquidationCall','compound_v3_usdc':'AbsorbDebt','morpho_blue':'Liquidate'}
        for protocol in CONTRACTS:
            selected=[e for e in events if e['protocol']==protocol and e['event_type']==units[protocol]]
            if not selected:skipped.append(protocol);continue
            samples=[selected[0]] if len(selected)==1 else [selected[0],selected[-1]]
            for event in samples:
                receipt=live('eth_getTransactionReceipt',[event['tx_hash']],rpc)
                matches=[log for log in receipt['logs'] if int(log['logIndex'],16)==int(event['log_index'])]
                ok=(len(matches)==1 and matches[0]['blockHash']==event['block_hash']
                    and matches[0]['address'].lower()==event['contract_address'])
                if ok:ok=decode_event(matches[0],specs[protocol][event['event_type']])==json.loads(event['decoded_json'])
                probes.append({'protocol':protocol,'tx_hash':event['tx_hash'],'log_index':event['log_index'],'matched':ok})
        # Preserve the existing list-shaped detail for a full pilot audit.
        detail=probes if not skipped else {'probes':probes,'protocols_without_liquidations':skipped}
        return bool(probes) and all(row['matched'] for row in probes),detail

    def boundaries():
        rows=[]
        for n in (manifest['start_block']-1,manifest['start_block'],manifest['end_block'],manifest['end_block']+1):
            block=live('eth_getBlockByNumber',[hex(n),False],rpc)
            rows.append({'block':n,'timestamp':int(block['timestamp'],16),'hash':block['hash']})
        ok=(rows[0]['timestamp']<ts(manifest['settings']['start'])<=rows[1]['timestamp']
            and rows[2]['timestamp']<ts(manifest['settings']['end'])<=rows[3]['timestamp'])
        return ok,rows

    def health_factors():
        users=[]
        for validation in validations:
            value=live('eth_call',[{'to':scope['registry']['pool'],
                       'data':calldata('getUserAccountData(address)',validation['account'])},hex(scope['block_number'])],rpc)
            w=words(value)
            if len(w)!=6:raise ValueError('getUserAccountData must return six ABI words')
            if not validation['hf_reported']:
                # HF is undefined at zero debt; check the debt instead of parsing ''.
                ok=D(validation['debt_reported_usd'])==0 and uint(w[1])==0
                fresh='undefined_zero_debt'
            else:
                fresh=str(D(uint(w[5]))/(D(10)**18))
                ok=abs(D(fresh)-D(validation['hf_reported']))<D('1e-15')
            users.append({'account':validation['account'],'hf_fresh':fresh,'matched':ok})
        return bool(users) and all(row['matched'] for row in users),users

    collect('fresh_rpc_receipts',receipts)
    collect('fresh_rpc_window_boundaries',boundaries)
    collect('fresh_rpc_snapshot_hf',health_factors)
    return checks

def run_audit(run_id,online=False):
    run=ROOT/'data/runs'/run_id; p=run/'processed'
    manifest=json.loads((run/'manifest.json').read_text(encoding='utf8'))
    if manifest['status']!='completed':raise ValueError('Run did not complete; finish pipeline before audit')
    scope=json.loads((p/'snapshot_scope.json').read_text(encoding='utf8'))
    files={f.name:read(f) for f in p.glob('*.csv')}
    events=files['events.csv']; liqs=files['liquidations.csv']; valued=files['aave_liquidations_valued.csv']; pos=files['positions.csv']
    results={}; checks=[]
    def check(name,condition,detail):
        checks.append({'check':name,'passed':bool(condition),'detail':detail})
    hashes={name:hashlib.sha256((run/name).read_bytes()).hexdigest()==digest for name,digest in manifest['outputs'].items()}
    check('file_hashes',all(hashes.values()),hashes)
    source_hashes={name:hashlib.sha256((ROOT/'data/sources'/name).read_bytes()).hexdigest()==digest for name,digest in manifest['source_hashes'].items()}
    check('source_hashes',all(source_hashes.values()),source_hashes)
    keys=[(e['chain_id'],e['tx_hash'],e['log_index']) for e in events]
    check('unique_events',len(set(keys))==len(keys),{'rows':len(keys),'unique':len(set(keys))})
    order=[tuple(int(e[k]) for k in ('block_number','transaction_index','log_index')) for e in events]
    check('execution_order',order==sorted(order),'block, transaction_index, log_index')
    check('time_bounds',all(ts(manifest['settings']['start'])<=ts(e['timestamp_utc'])<ts(manifest['settings']['end']) for e in events),'All selected events in [start,end) UTC')
    required=('protocol','contract_address','event_type','block_number','timestamp_utc','tx_hash','transaction_index','log_index','market_id')
    missing={k:sum(not e[k] for e in events) for k in required}
    check('required_identifiers',not any(missing.values()),missing)
    specs={protocol:parse_events((ROOT/'data/sources'/source).read_text()) for protocol,(_,source,_) in CONTRACTS.items()}
    with closing(sqlite3.connect(run/'raw.sqlite')) as db:
        raw=db.execute('SELECT protocol,name,raw,decoded FROM logs ORDER BY block,tx,idx').fetchall()
        decode_bad=[]
        for protocol,name,raw_s,decoded_s in raw:
            if decode_event(json.loads(raw_s),specs[protocol][name])!=json.loads(decoded_s):decode_bad.append(json.loads(raw_s)['transactionHash'])
        check('raw_decode_replay',not decode_bad,{'checked':len(raw),'mismatches':len(decode_bad)})
        coverage=[]
        for protocol in CONTRACTS:
            ranges=db.execute('SELECT start,end FROM coverage WHERE protocol=? ORDER BY start',(protocol,)).fetchall()
            expected=manifest['start_block']; ok=True
            for a,b in ranges:
                ok &= a==expected; expected=b+1
            ok &= expected==manifest['end_block']+1
            coverage.append({'protocol':protocol,'ranges':ranges,'continuous':bool(ok)})
        check('coverage_ledger',all(r['continuous'] for r in coverage),coverage)
    # Independent row-level price * amount arithmetic, using original oracle RPC cache.
    value_error=D(0); cache_error=D(0)
    oracle=scope['registry']['oracle']
    decimals={r['token_address']:int(r['decimals']) for r in files['aave_reserves.csv']}
    for r in valued:
        expected=D(r['debt_repaid_raw'])/(D(10)**decimals[r['debt_token']])*D(r['debt_price_usd'])
        value_error=max(value_error,abs(expected-D(r['debt_repaid_usd'])))
        params=[{'to':oracle,'data':calldata('getAssetPrice(address)',r['debt_token'])},hex(int(r['block_number']))]
        price=D(uint(words(cached('eth_call',params))[0]))
        base=D(uint(words(cached('eth_call',[{'to':oracle,'data':calldata('BASE_CURRENCY_UNIT()')},hex(int(r['block_number']))]))[0]))
        cache_error=max(cache_error,abs(price/base-D(r['debt_price_usd'])))
    check('valuation_arithmetic',value_error<D('1e-20') and cache_error==0,{'max_usd_error':str(value_error),'max_price_cache_error':str(cache_error),'rows':len(valued)})
    total=sum((D(r['debt_repaid_usd']) for r in valued),D(0))
    summaries=[]
    for r in files['rq2_concentration.csv']:
        groups=defaultdict(lambda:D(0))
        for row in valued:groups[row[r['group_by']]]+=D(row['debt_repaid_usd'])
        amounts=sorted(groups.values(),reverse=True)
        metrics={'top_1_share':amounts[0]/total,'top_10_share':sum(amounts[:10])/total,'hhi':sum((v/total)**2 for v in amounts)}
        ok=int(r['categories'])==len(groups) and all(abs(D(r[k])-v)<D('1e-50') for k,v in metrics.items())
        summaries.append({'dimension':r['group_by'],'categories':len(groups),**{k:str(v) for k,v in metrics.items()},'passed':ok})
    check('concentration_recalculation',all(r['passed'] for r in summaries),summaries)
    # Recompute all 36 static scenarios from CSV, explicitly parsing booleans.
    stress_bad=[]; wallets=defaultdict(list)
    for r in pos:
        if r['validation_status']=='passed':wallets[r['account']].append(r)
    for scenario in files['rq1_sample_stress.csv']:
        amount=D(0); count=0
        for rows in wallets.values():
            weighted=D(0); debt=D(0)
            for r in rows:
                shock=D(scenario['eth_shock']) if r['symbol']=='WETH' else D(scenario['btc_shock']) if r['symbol']=='WBTC' else D(0)
                price=D(r['price_usd'])*(1+shock)
                if r['collateral_enabled']=='True':weighted+=D(r['supply_amount'])*price*D(r['liquidation_threshold'])
                debt+=D(r['debt_amount'])*price
            if debt and weighted<debt:count+=1;amount+=debt
        if count!=int(scenario['accounts_at_risk']) or abs(amount-D(scenario['eligible_debt_usd']))>D('1e-20'):stress_bad.append(scenario)
    check('stress_recalculation',not stress_bad,{'scenarios':len(files['rq1_sample_stress.csv']),'mismatches':len(stress_bad)})
    units={'aave_v3':'LiquidationCall','compound_v3_usdc':'AbsorbDebt','morpho_blue':'Liquidate'}
    hourly=files['hourly_counts.csv']
    panels=[]
    for protocol,event in units.items():
        a=sum(int(r['liquidation_count']) for r in hourly if r['protocol']==protocol)
        b=sum(r['protocol']==protocol and r['event_type']==event for r in events)
        panels.append({'protocol':protocol,'panel_count':a,'event_count':b,'matched':a==b})
    check('hourly_count_reconciliation',all(x['matched'] for x in panels),panels)
    results.update(audit_date_local=datetime.now(timezone(timedelta(hours=7))).strftime('%d/%m/%Y'),
        audit_mode='live' if online else 'offline',run_id=run_id,window=manifest['settings'],
        blocks=[manifest['start_block'],manifest['end_block']],total_events=len(events),
        protocol_counts=dict(Counter(e['protocol'] for e in events)),event_counts=dict(Counter(e['protocol']+':'+e['event_type'] for e in events)),
        file_inventory=[{'file':name,'rows':len(rows),'columns':len(rows[0]) if rows else 0,'bytes':(p/name).stat().st_size} for name,rows in files.items()],
        unique_transactions=len({e['tx_hash'] for e in events}),blocks_with_events=len({e['block_number'] for e in events}),
        aave_liquidation_transactions=len({r['tx_hash'] for r in valued}),
        total_aave_repaid_usd=str(total),liquidation_related_rows=len(liqs),
        scope=scope,concentration=summaries,validation=files['position_validation.csv'],
        receipt_transactions=len({r['tx_hash'] for r in files['token_transfers_sample.csv']}),
        missing_liquidation_tokens={protocol:{k:sum(not r[k] for r in liqs if r['protocol']==protocol) for k in ('debt_token','collateral_token')} for protocol in CONTRACTS},
        checks=checks)
    results['hourly_rows']=hourly
    if online:
        rpc=Rpc(ROOT/'data/rpc_cache')
        checks.extend(live_checks(rpc,manifest,scope,events,results['validation'],specs))
        results['live_rpc']={'configured_endpoints':len(rpc.urls),'http_requests':rpc.requests,'cache_bypassed':True}
    results['all_executed_checks_passed']=all(c['passed'] for c in checks)
    results['checked_at_utc']=datetime.now(timezone.utc).isoformat()
    target=run/'audit';target.mkdir(exist_ok=True)
    (target/'audit_results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'checks':len(checks),'passed':sum(c['passed'] for c in checks),'total_events':len(events),
        'files':len(files),'live':online,'all_checks_passed':results['all_executed_checks_passed']}))
    return results

def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');parser.add_argument('--run-id',default='stress_20250203_smoke')
    a=parser.parse_args(argv)
    try:
        results=run_audit(a.run_id,a.live)
    except (RpcError,OSError,ValueError,KeyError,sqlite3.Error) as exc:
        parser.exit(1,f'Audit could not finish: {exc}\n')
    return 0 if results['all_executed_checks_passed'] else 1


if __name__=='__main__':raise SystemExit(main())
