"""Independent arithmetic / integrity audit of an existing pilot run."""
import argparse
import csv
import hashlib
import json
import sqlite3
import urllib.request
from collections import Counter,defaultdict
from contextlib import closing
from datetime import datetime,timezone
from decimal import Decimal,getcontext
from pathlib import Path
from .pipeline import ROOT,CONTRACTS,ts
from .evm import addr,words,uint,calldata,parse_events,decode_event

getcontext().prec=70
D=Decimal

def read(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def cached(method,params):
    key=json.dumps([method,params],sort_keys=True,separators=(',',':')).encode()
    return json.loads((ROOT/'data/rpc_cache'/(hashlib.sha256(key).hexdigest()+'.json')).read_text())

def live(method,params):
    errors=[]
    for url in ('https://rpc.flashbots.net','https://eth-mainnet.public.blastapi.io'):
        try:
            req=urllib.request.Request(url,json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}).encode(),
                {'Content-Type':'application/json','User-Agent':'DeFiResearchAudit/1.0'})
            with urllib.request.urlopen(req,timeout=35) as f:r=json.load(f)
            if 'error' in r or r.get('result') is None:
                errors.append('RPC error or missing historical result');continue
            return r['result']
        except Exception as exc:errors.append(type(exc).__name__)
    raise RuntimeError('Fresh RPC unavailable: '+','.join(errors))

def run_audit(run_id,online=False):
    run=ROOT/'data/runs'/run_id; p=run/'processed'
    manifest=json.loads((run/'manifest.json').read_text()); scope=json.loads((p/'snapshot_scope.json').read_text())
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
    results.update(audit_date_local='18/10/2026',run_id=run_id,window=manifest['settings'],
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
        probes=[]
        for protocol in CONTRACTS:
            selected=[e for e in events if e['protocol']==protocol and e['event_type']==units[protocol]]
            for e in [selected[0],selected[-1]]:
                receipt=live('eth_getTransactionReceipt',[e['tx_hash']])
                matches=[log for log in receipt['logs'] if int(log['logIndex'],16)==int(e['log_index'])]
                ok=len(matches)==1 and matches[0]['blockHash']==e['block_hash'] and matches[0]['address'].lower()==e['contract_address']
                if ok:ok=decode_event(matches[0],specs[protocol][e['event_type']])==json.loads(e['decoded_json'])
                probes.append({'protocol':protocol,'tx_hash':e['tx_hash'],'log_index':e['log_index'],'matched':ok})
        check('fresh_rpc_receipts',all(x['matched'] for x in probes),probes)
        boundary=[]
        for n in [manifest['start_block']-1,manifest['start_block'],manifest['end_block'],manifest['end_block']+1]:
            b=live('eth_getBlockByNumber',[hex(n),False]); boundary.append({'block':n,'timestamp':int(b['timestamp'],16),'hash':b['hash']})
        check('fresh_rpc_window_boundaries',boundary[0]['timestamp']<ts(manifest['settings']['start'])<=boundary[1]['timestamp'] and
            boundary[2]['timestamp']<ts(manifest['settings']['end'])<=boundary[3]['timestamp'],boundary)
        users=[]
        for v in results['validation']:
            value=live('eth_call',[{'to':scope['registry']['pool'],'data':calldata('getUserAccountData(address)',v['account'])},hex(scope['block_number'])])
            w=words(value);hf=D(uint(w[5]))/(D(10)**18)
            ok=abs(hf-D(v['hf_reported']))<D('1e-15')
            users.append({'account':v['account'],'hf_fresh':str(hf),'matched':ok})
        check('fresh_rpc_snapshot_hf',all(x['matched'] for x in users),users)
        results['live_endpoints']=['https://rpc.flashbots.net','https://eth-mainnet.public.blastapi.io']
    results['all_executed_checks_passed']=all(c['passed'] for c in checks)
    results['checked_at_utc']=datetime.now(timezone.utc).isoformat()
    target=run/'audit';target.mkdir(exist_ok=True)
    (target/'audit_results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'checks':len(checks),'passed':sum(c['passed'] for c in checks),'total_events':len(events),
        'files':len(files),'live':online,'all_checks_passed':results['all_executed_checks_passed']}))
    return results

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');parser.add_argument('--run-id',default='stress_20250203_smoke')
    a=parser.parse_args();run_audit(a.run_id,a.live)
