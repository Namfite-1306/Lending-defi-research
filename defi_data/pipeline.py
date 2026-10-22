import argparse
import csv
import hashlib
import json
import re
import sqlite3
from collections import Counter,defaultdict
from contextlib import closing
from datetime import datetime,timezone
from decimal import Decimal,getcontext
from pathlib import Path
from .evm import addr,address_array,calldata,decode_event,decode_string,parse_events,uint,words
from .rpc import Rpc,RpcError

getcontext().prec=60
D=Decimal
ROOT=Path(__file__).resolve().parents[1]
ZERO='0x'+'0'*40
PROVIDER='0x2f39d218133afab8f2b819b1066c7e434ad94e9e'
CONTRACTS={
 'aave_v3':('0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2','IPool.sol',
             ['Supply','Borrow','Repay','Withdraw','LiquidationCall','ReserveUsedAsCollateralEnabled','ReserveUsedAsCollateralDisabled','UserEModeSet']),
 'compound_v3_usdc':('0xc3d688b66703497daa19211eedff47f25384cdc3','CometMainInterface.sol',
             ['Supply','Withdraw','SupplyCollateral','WithdrawCollateral','Transfer','TransferCollateral','AbsorbDebt','AbsorbCollateral','BuyCollateral']),
 'morpho_blue':('0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb','EventsLib.sol',
             ['Supply','Withdraw','Borrow','Repay','SupplyCollateral','WithdrawCollateral','Liquidate'])}

def utc(ts): return datetime.fromtimestamp(ts,timezone.utc).isoformat()
def ts(text):
    dt=datetime.fromisoformat(text.replace('Z','+00:00'))
    if dt.tzinfo is None: raise ValueError('Dates must include timezone, e.g. 2025-02-03T00:00:00Z')
    return int(dt.timestamp())
def save_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
def csv_write(path,rows,fields=None):
    path.parent.mkdir(parents=True,exist_ok=True)
    if not fields: fields=list(dict.fromkeys(k for row in rows for k in row))
    if not fields:
        fields={
            'events.csv':['chain_id','protocol','event_type','block_number','timestamp_utc','tx_hash','log_index','account'],
            'liquidations.csv':['chain_id','protocol','event_type','block_number','tx_hash','log_index','borrower','liquidator','debt_token','collateral_token','debt_repaid_raw','collateral_seized_raw','measurement'],
            'blocks.csv':['block_number','block_hash','timestamp_utc'],
            'positions.csv':['chain_id','protocol','block_number','account','token_address','supply_amount','debt_amount','validation_status'],
            'position_validation.csv':['account','block_number','status','max_relative_error'],
            'token_transfers_sample.csv':['tx_hash','block_number','log_index','token_address','from_address','to_address','amount_raw'],
            'aave_liquidations_valued.csv':['protocol','tx_hash','log_index','borrower','liquidator','debt_token','collateral_token','debt_repaid_usd','price_timing']
        }.get(path.name,['no_records'])
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='raise'); writer.writeheader(); writer.writerows(rows)
def call_request(to,sig,args,block):
    return ('eth_call',[{'to':to,'data':calldata(sig,*args)},hex(block)])
def call(rpc,to,sig,args,block): return words(rpc.one(*call_request(to,sig,args,block)))
def connect(path):
    conn=sqlite3.connect(path)
    conn.execute('CREATE TABLE IF NOT EXISTS logs (chain INTEGER, tx TEXT, idx INTEGER, block INTEGER, hash TEXT, protocol TEXT, name TEXT, raw TEXT, decoded TEXT, PRIMARY KEY(chain,tx,idx))')
    conn.execute('CREATE TABLE IF NOT EXISTS coverage (protocol TEXT, start INTEGER, end INTEGER, start_hash TEXT, end_hash TEXT, PRIMARY KEY(protocol,start,end))')
    return conn

def crawl(rpc,conn,start,end,chunk):
    for protocol,(address,source,names) in CONTRACTS.items():
        specs=parse_events((ROOT/'data/sources'/source).read_text())
        by_topic={specs[name]['topic']: (name,specs[name]) for name in names}
        for lo in range(start,end+1,chunk):
            hi=min(lo+chunk-1,end)
            if conn.execute('SELECT 1 FROM coverage WHERE protocol=? AND start=? AND end=?',(protocol,lo,hi)).fetchone():
                print(f'{protocol}: cached coverage {lo}-{hi}',flush=True); continue
            logs=rpc.logs(address,list(by_topic),lo,hi)
            values=[]
            for log in logs:
                if log.get('removed'): raise ValueError('Removed/reorg log returned')
                name,spec=by_topic[log['topics'][0]]
                decoded=decode_event(log,spec)
                values.append((1,log['transactionHash'],int(log['logIndex'],16),int(log['blockNumber'],16),
                    log['blockHash'],protocol,name,json.dumps(log),json.dumps(decoded)))
            with conn:
                conn.executemany('INSERT OR REPLACE INTO logs VALUES (?,?,?,?,?,?,?,?,?)',values)
                conn.execute('INSERT INTO coverage VALUES (?,?,?,?,?)',(protocol,lo,hi,rpc.block(lo)['hash'],rpc.block(hi)['hash']))
            print(f'{protocol}: {lo}-{hi}: {len(logs)} events',flush=True)

def base_row(log,decoded,timestamp):
    protocol,name,raw=log
    return {'chain_id':1,'protocol':protocol,'contract_address':raw['address'].lower(),
       'event_type':name,'block_number':int(raw['blockNumber'],16),'block_hash':raw['blockHash'],
       'timestamp_utc':utc(timestamp),'tx_hash':raw['transactionHash'],
       'transaction_index':int(raw['transactionIndex'],16),'log_index':int(raw['logIndex'],16),
       'market_id':decoded.get('id',raw['address'].lower())}

def normalize(rpc,conn,start,end,out,window_start=None,window_end=None):
    records=conn.execute('SELECT protocol,name,raw,decoded FROM logs WHERE block BETWEEN ? AND ? ORDER BY block,tx,idx',(start,end)).fetchall()
    numbers=sorted({int(json.loads(raw)['blockNumber'],16) for _,_,raw,_ in records})
    blocks=rpc.many([('eth_getBlockByNumber',[hex(n),False]) for n in numbers])
    timestamps={n:int(b['timestamp'],16) for n,b in zip(numbers,blocks)}
    hashes={n:b['hash'] for n,b in zip(numbers,blocks)}
    events=[]; liquidations=[]; decode_errors=[]
    for protocol,name,raw_json,data_json in records:
        raw=json.loads(raw_json); data=json.loads(data_json)
        if raw['blockHash']!=hashes[int(raw['blockNumber'],16)]: raise ValueError('Reorg mismatch; use a fresh run/cache')
        row=base_row((protocol,name,raw),data,timestamps[int(raw['blockNumber'],16)])
        row['account']=data.get('onBehalfOf',data.get('onBehalf',data.get('borrower',data.get('user',data.get('dst',data.get('src',''))))))
        row['actor']=data.get('caller',data.get('liquidator',data.get('absorber',data.get('repayer',data.get('from',data.get('user',''))))))
        row['token_address']=data.get('reserve',data.get('asset',''))
        row['amount_raw']=str(data.get('amount',data.get('assets','')))
        row['decoded_json']=data_json
        events.append(row)
        if name in ('LiquidationCall','Liquidate','AbsorbDebt','AbsorbCollateral','BuyCollateral'):
            liq={**row,'borrower':data.get('borrower',data.get('user','')),
                 'liquidator':data.get('liquidator',data.get('caller',data.get('absorber',data.get('buyer','')))),
                 'debt_token':data.get('debtAsset',''),'collateral_token':data.get('collateralAsset',data.get('asset','')),
                 'debt_repaid_raw':str(data.get('debtToCover',data.get('repaidAssets',data.get('basePaidOut','')))),
                 'collateral_seized_raw':str(data.get('liquidatedCollateralAmount',data.get('seizedAssets',data.get('collateralAbsorbed','')))),
                 'bad_debt_raw':str(data.get('badDebtAssets','')),
                 'measurement':{'LiquidationCall':'debt_repayment_and_collateral_seizure','Liquidate':'debt_repayment_and_collateral_seizure',
                    'AbsorbDebt':'protocol_absorption_debt','AbsorbCollateral':'protocol_absorption_collateral','BuyCollateral':'protocol_collateral_purchase'}[name]}
            liquidations.append(liq)
    events.sort(key=lambda e:(e['block_number'],e['transaction_index'],e['log_index']))
    liquidations.sort(key=lambda e:(e['block_number'],e['transaction_index'],e['log_index']))
    csv_write(out/'events.csv',events)
    csv_write(out/'liquidations.csv',liquidations)
    csv_write(out/'blocks.csv',[{'block_number':n,'block_hash':hashes[n],'timestamp_utc':utc(timestamps[n])} for n in numbers])
    # Continuous hourly panel, including verified zero-event hours, with distinct liquidation units.
    units={'aave_v3':'LiquidationCall','compound_v3_usdc':'AbsorbDebt','morpho_blue':'Liquidate'}
    counts=Counter((e['protocol'],int(datetime.fromisoformat(e['timestamp_utc']).timestamp())//3600) for e in events if e['event_type']==units[e['protocol']])
    start_ts=window_start if window_start is not None else int(rpc.block(start)['timestamp'],16)
    end_ts=window_end if window_end is not None else int(rpc.block(end)['timestamp'],16)+1
    panel=[]
    for p in CONTRACTS:
        for h in range(start_ts//3600,(end_ts-1)//3600+1):
            observed=max(0,min(end_ts,(h+1)*3600)-max(start_ts,h*3600))
            panel.append({'protocol':p,'hour_utc':utc(h*3600),'liquidation_count':counts[p,h],
                'observed_seconds':observed,'partial_hour':observed<3600,'unit':units[p]})
    csv_write(out/'hourly_counts.csv',panel)
    return events,liquidations

def registry(rpc,block):
    pool=addr(call(rpc,PROVIDER,'getPool()',[],block)[0])
    oracle=addr(call(rpc,PROVIDER,'getPriceOracle()',[],block)[0])
    provider=addr(call(rpc,PROVIDER,'getPoolDataProvider()',[],block)[0])
    return pool,oracle,provider

def metadata(rpc,token_addresses,block):
    calls=[]
    for token in token_addresses:
        calls += [call_request(token,'symbol()',[],block),call_request(token,'decimals()',[],block)]
    results=rpc.many(calls)
    return {token:{'symbol':decode_string(results[2*i]),'decimals':uint(words(results[2*i+1])[0])} for i,token in enumerate(token_addresses)}

def snapshot(rpc,events,block,max_wallets,out,wallet_file=None):
    pool,oracle,provider=registry(rpc,block)
    reserves=address_array(rpc.one(*call_request(pool,'getReservesList()',[],block)))
    meta=metadata(rpc,reserves,block)
    # Discovery is deliberately labelled a window sample, never the full borrower universe.
    discovered=[]
    for kinds in ({'LiquidationCall'},{'Borrow'},{'Supply','Withdraw','Repay'}):
        found=sorted({e['account'] for e in events if e['protocol']=='aave_v3' and e['event_type'] in kinds and e['account'] and e['account']!=ZERO})
        discovered.extend(w for w in found if w not in discovered)
    if wallet_file:
        discovered=sorted({line.strip().lower() for line in Path(wallet_file).read_text().splitlines() if line.strip()})
        discovery='provided_wallet_list_universe_not_verified'
    else: discovery='event_window_sample_lookahead_selected'
    wallets=discovered[:max_wallets] if max_wallets else discovered
    for wallet in wallets:
        if not re.fullmatch(r'0x[0-9a-f]{40}',wallet): raise ValueError('Invalid wallet address')
    if addr(call(rpc,oracle,'BASE_CURRENCY()',[],block)[0])!=ZERO:
        raise ValueError('Oracle base currency is not USD; conversion required')
    base=D(uint(call(rpc,oracle,'BASE_CURRENCY_UNIT()',[],block)[0]))
    cfgs=rpc.many([call_request(provider,'getReserveConfigurationData(address)',[r],block) for r in reserves])
    prices=rpc.many([call_request(oracle,'getAssetPrice(address)',[r],block) for r in reserves])
    reserve_rows=[]
    for token,cfg,price in zip(reserves,cfgs,prices):
        w=words(cfg); meta[token]['price']=D(uint(words(price)[0]))/base
        meta[token]['lt']=D(uint(w[2]))/10000
        reserve_rows.append({'block_number':block,'token_address':token,**meta[token],
             'ltv':str(D(uint(w[1]))/10000),'liquidation_bonus_factor':str(D(uint(w[3]))/10000),
             'source':'historical_contract_call','config_raw':json.dumps([uint(v) for v in w])})
    positions=[]; validations=[]
    for wallet in wallets:
        account=call(rpc,pool,'getUserAccountData(address)',[wallet],block)
        emode=uint(call(rpc,pool,'getUserEMode(address)',[wallet],block)[0])
        balances=rpc.many([call_request(provider,'getUserReserveData(address,address)',[r,wallet],block) for r in reserves])
        collateral=D(0); debt=D(0); weighted=D(0); local=[]
        for token,result in zip(reserves,balances):
            w=words(result)
            if len(w)!=9: raise ValueError('Unsupported data-provider ABI; do not silently reinterpret balances')
            supply=uint(w[0]); debt_raw=uint(w[1])+uint(w[2]); enabled=bool(uint(w[8]))
            if not supply and not debt_raw: continue
            m=meta[token]; unit=D(10)**m['decimals']; supplied=D(supply)/unit; borrowed=D(debt_raw)/unit
            cv=supplied*m['price'] if enabled else D(0); dv=borrowed*m['price']
            collateral+=cv; debt+=dv; weighted+=cv*m['lt']
            local.append({'chain_id':1,'protocol':'aave_v3','market_id':pool,'block_number':block,
                'account':wallet,'token_address':token,'symbol':m['symbol'],'decimals':m['decimals'],
                'supply_raw':str(supply),'debt_raw':str(debt_raw),'supply_amount':str(supplied),'debt_amount':str(borrowed),
                'collateral_enabled':enabled,'price_usd':str(m['price']),'liquidation_threshold':str(m['lt']),
                'collateral_usd':str(cv),'debt_usd':str(dv),'emode':emode,'discovery_scope':discovery})
        reported_c=D(uint(account[0]))/base; reported_d=D(uint(account[1]))/base
        reported_hf=D(uint(account[5]))/D(10)**18 if uint(account[1]) else None
        calculated=weighted/debt if debt else None
        tolerance=D('.0001')
        errors=[abs(collateral-reported_c)/max(reported_c,D(1)),abs(debt-reported_d)/max(reported_d,D(1))]
        hf_error=abs(calculated-reported_hf)/max(reported_hf,D(1)) if calculated is not None and reported_hf is not None else None
        if hf_error is not None: errors.append(hf_error)
        status='unsupported_emode' if emode else ('passed' if max(errors)<=tolerance else 'failed')
        for row in local: row['validation_status']=status
        positions.extend(local)
        validations.append({'account':wallet,'block_number':block,'emode':emode,'status':status,
            'collateral_calculated_usd':str(collateral),'collateral_reported_usd':str(reported_c),
            'debt_calculated_usd':str(debt),'debt_reported_usd':str(reported_d),
            'hf_calculated':str(calculated) if calculated is not None else '',
            'hf_reported':str(reported_hf) if reported_hf is not None else '',
            'max_relative_error':str(max(errors)),'relative_tolerance':str(tolerance)})
        print(f'snapshot {wallet}: {len(local)} tokens, {status}',flush=True)
    csv_write(out/'aave_reserves.csv',reserve_rows)
    csv_write(out/'positions.csv',positions)
    csv_write(out/'position_validation.csv',validations)
    save_json(out/'snapshot_scope.json',{'block_number':block,'block_hash':rpc.block(block)['hash'],
        'registry':{'pool':pool,'oracle':oracle,'data_provider':provider},'wallets_discovered':len(discovered),
        'wallets_sampled':len(wallets),'scope':discovery,'is_full_market':False,
        'emode_policy':'Export raw balances but exclude E-mode from stress until category rules implemented and validated.'})
    return positions,validations

def stress(positions,out):
    groups=defaultdict(list)
    for p in positions:
        if p['validation_status']=='passed': groups[p['account']].append(p)
    scenarios=[]
    # Only explicit WETH/WBTC risk-factor mapping; derivatives are not silently assumed perfectly pegged.
    for eth in (0,-.1,-.2,-.3,-.4,-.5):
        for btc in (0,-.1,-.2,-.3,-.4,-.5):
            at_risk=0; debt_risk=D(0)
            for rows in groups.values():
                numerator=D(0); denominator=D(0)
                for p in rows:
                    shock=D(str(eth if p['symbol']=='WETH' else btc if p['symbol']=='WBTC' else 0))
                    price=D(p['price_usd'])*(1+shock)
                    numerator+=(D(p['supply_amount'])*price*D(p['liquidation_threshold']) if p['collateral_enabled'] else 0)
                    denominator+=D(p['debt_amount'])*price
                if denominator and numerator<denominator: at_risk+=1; debt_risk+=denominator
            scenarios.append({'eth_shock':eth,'btc_shock':btc,'accounts_at_risk':at_risk,
                'eligible_debt_usd':str(debt_risk),'validated_sample_accounts':len(groups),
                'scope':'sample_only_not_actual_liquidation_volume','risk_factors':'WETH/WBTC only; all other tokens fixed'})
    csv_write(out/'rq1_sample_stress.csv',scenarios)

def enrich_liquidations(rpc,liqs,out):
    tokens=set()
    for row in liqs:
        if row['protocol']=='aave_v3': tokens.update([row['debt_token'],row['collateral_token']])
    if not tokens:
        csv_write(out/'aave_liquidations_valued.csv',[])
        return []
    first=min(int(r['block_number']) for r in liqs)
    meta=metadata(rpc,sorted(tokens),first)
    # Exact oracle reads at event block END. This is not pre-transaction pricing.
    result=[]; requests=[]; refs=[]
    block_ids=sorted({int(r['block_number']) for r in liqs if r['protocol']=='aave_v3'})
    oracle_results=rpc.many([call_request(PROVIDER,'getPriceOracle()',[],b) for b in block_ids])
    oracles={b:addr(words(value)[0]) for b,value in zip(block_ids,oracle_results)}
    for row in liqs:
        if row['protocol']!='aave_v3': continue
        b=int(row['block_number']); oracle=oracles[b]
        requests.extend([call_request(oracle,'getAssetPrice(address)',[row['debt_token']],b),call_request(oracle,'BASE_CURRENCY_UNIT()',[],b)])
        refs.append(row)
    vals=rpc.many(requests)
    for i,row in enumerate(refs):
        token=row['debt_token']; quantity=D(row['debt_repaid_raw'])/(D(10)**meta[token]['decimals'])
        price=D(uint(words(vals[2*i])[0]))/D(uint(words(vals[2*i+1])[0]))
        result.append({**row,'debt_symbol':meta[token]['symbol'],'debt_repaid_amount':str(quantity),
            'debt_price_usd':str(price),'debt_repaid_usd':str(quantity*price),'price_timing':'event_block_end_oracle'})
    csv_write(out/'aave_liquidations_valued.csv',result)
    return result

def concentration(valued,out):
    rows=[]
    for field in ('borrower','liquidator','collateral_token','debt_token'):
        totals=defaultdict(lambda:D(0))
        for row in valued: totals[row[field]]+=D(row['debt_repaid_usd'])
        total=sum(totals.values()); shares=sorted(totals.values(),reverse=True)
        rows.append({'protocol':'aave_v3','group_by':field,'categories':len(totals),'debt_repaid_usd':str(total),
            'top_1_share':str(shares[0]/total) if total else '',
            'top_10_share':str(sum(shares[:10])/total) if total else '',
            'hhi':str(sum((v/total)**2 for v in shares)) if total else '',
            'unit':'repaid_debt_usd_at_event_block_end_oracle'})
    csv_write(out/'rq2_concentration.csv',rows)

def activity_candidates(events,out):
    activity=defaultdict(Counter); grouped=defaultdict(list)
    for row in events:
        if row['account']:
            activity[(row['account'],row['protocol'],row['market_id'])][row['event_type']]+=1
        if row['protocol']=='aave_v3': grouped[(row['tx_hash'],row['account'])].append(row)
    csv_write(out/'account_market_activity.csv',[
        {'account':a,'protocol':p,'market_id':m,'event_count':sum(c.values()),
         'events_json':json.dumps(dict(c)),'interpretation':'observed_activity_not_balance_or_direct_exposure'}
        for (a,p,m),c in sorted(activity.items())])
    candidates=[]
    for (tx,account),group in grouped.items():
        for borrow in [r for r in group if r['event_type']=='Borrow']:
            for supply in [r for r in group if r['event_type']=='Supply' and r['log_index']>borrow['log_index']]:
                candidates.append({'tx_hash':tx,'account':account,'borrow_log_index':borrow['log_index'],
                    'supply_log_index':supply['log_index'],'borrow_token':borrow['token_address'],
                    'supply_token':supply['token_address'],'confirmed_recursive_leverage':False,
                    'interpretation':'same_transaction_borrow_then_supply_motif_requires_flow_verification'})
    csv_write(out/'rq3_borrow_supply_candidates.csv',candidates,
        ['tx_hash','account','borrow_log_index','supply_log_index','borrow_token','supply_token','confirmed_recursive_leverage','interpretation'])

def hourly_oracle_prices(rpc,start,end,out):
    start_ts=int(rpc.block(start)['timestamp'],16); end_ts=int(rpc.block(end)['timestamp'],16)
    points=[start-1]
    for stamp in range((start_ts//3600+1)*3600,end_ts+1,3600):
        lo,hi=start,end
        while lo<hi:
            mid=(lo+hi)//2
            if int(rpc.block(mid)['timestamp'],16)<stamp: lo=mid+1
            else: hi=mid
        points.append(lo-1)
    if points[-1]!=end: points.append(end)
    tokens={'WETH':'0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2',
            'WBTC':'0x2260fac5e5542a773aa44fbcfedf7c193bc2c599',
            'USDC':'0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'}
    oracles=rpc.many([call_request(PROVIDER,'getPriceOracle()',[],b) for b in points])
    rows=[]
    for b,result in zip(points,oracles):
        oracle=addr(words(result)[0]); names=list(tokens)
        data=rpc.many([call_request(oracle,'BASE_CURRENCY()',[],b),call_request(oracle,'BASE_CURRENCY_UNIT()',[],b)]+
             [call_request(oracle,'getAssetPrice(address)',[tokens[n]],b) for n in names])
        if addr(words(data[0])[0])!=ZERO: raise ValueError('Non-USD oracle requires conversion')
        base=D(uint(words(data[1])[0])); timestamp=int(rpc.block(b)['timestamp'],16)
        for name,value in zip(names,data[2:]):
            rows.append({'block_number':b,'timestamp_utc':utc(timestamp),'symbol':name,
                'token_address':tokens[name],'price_usd':str(D(uint(words(value)[0]))/base),
                'price_type':'aave_oracle','timing':'last_block_before_hour_boundary_or_window_start'})
    csv_write(out/'oracle_prices_hourly.csv',rows)

def receipt_flows(rpc,events,limit,out):
    preferred=[e for e in events if e['protocol']=='aave_v3' and e['event_type']=='Borrow']
    preferred += [e for e in events if e['protocol']=='aave_v3']
    hashes=list(dict.fromkeys(e['tx_hash'] for e in preferred))[:limit]
    receipts=rpc.many([('eth_getTransactionReceipt',[h]) for h in hashes])
    from .evm import topic
    transfer=topic('Transfer(address,address,uint256)'); rows=[]
    for receipt in receipts:
        for log in receipt['logs']:
            if len(log['topics'])!=3 or log['topics'][0]!=transfer: continue
            w=words(log['data'])
            if len(w)!=1: continue
            rows.append({'tx_hash':receipt['transactionHash'],'block_number':int(receipt['blockNumber'],16),
                'log_index':int(log['logIndex'],16),'token_address':log['address'].lower(),
                'from_address':addr(log['topics'][1]),'to_address':addr(log['topics'][2]),'amount_raw':str(uint(w[0])),
                'scope':'sample_of_transactions_in_event_window','proves_recursive_leverage':False})
    csv_write(out/'token_transfers_sample.csv',rows)
    return len(receipts)

def main():
    parser=argparse.ArgumentParser(description='Read-only Ethereum DeFi data collection; UTC [start,end).')
    parser.add_argument('--start',default='2025-02-03T00:00:00Z')
    parser.add_argument('--end',default='2025-02-03T03:00:00Z')
    parser.add_argument('--run-id',default='stress_20250203_smoke')
    parser.add_argument('--chunk',type=int,default=500)
    parser.add_argument('--max-wallets',type=int,default=5,help='0 = all DISCOVERED wallets, not all market wallets')
    parser.add_argument('--wallet-file',help='One address per line; list coverage is not presumed complete')
    parser.add_argument('--receipts',type=int,default=20)
    parser.add_argument('--skip-snapshot',action='store_true')
    parser.add_argument('--skip-valuations',action='store_true')
    args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+',args.run_id): parser.error('Unsafe run-id')
    if args.chunk<1 or args.max_wallets<0 or args.receipts<0: parser.error('Invalid limits')
    if ts(args.end)<=ts(args.start): parser.error('end must follow start')
    run=ROOT/'data/runs'/args.run_id; run.mkdir(parents=True,exist_ok=True)
    settings={k:v for k,v in vars(args).items()}
    config_path=run/'settings.json'
    if config_path.exists() and json.loads(config_path.read_text())!=settings:
        parser.error('Run-id already exists with different settings; choose a new run-id')
    save_json(config_path,settings)
    rpc=Rpc(ROOT/'data/rpc_cache')
    manifest={'status':'running','started_utc':datetime.now(timezone.utc).isoformat(),'settings':settings,
        'data_origin':'ethereum_mainnet_rpc','not_synthetic':True,'research_ready':False}
    save_json(run/'manifest.json',manifest)
    try:
        if int(rpc.one('eth_chainId',[],cache=False),16)!=1: raise ValueError('Expected Ethereum chain 1')
        head=int(rpc.one('eth_blockNumber',[],cache=False),16)-64
        range_path=run/'block_range.json'
        if range_path.exists():
            pinned=json.loads(range_path.read_text())
            start,end=pinned['start_block'],pinned['end_block']
        else:
            start=rpc.block_at(ts(args.start),head); end=rpc.block_at(ts(args.end),head)-1
            save_json(range_path,{'start_block':start,'end_block':end})
        if end>head: raise ValueError('Pinned range is not sufficiently confirmed')
        if end<start: raise ValueError('Empty block range')
        manifest.update(start_block=start,end_block=end,start_hash=rpc.block(start)['hash'],end_hash=rpc.block(end)['hash'])
        print(f'Fixed finalized range: {start}-{end}',flush=True)
        rpc.preflight(start,end,run/'rpc_preflight.json',require_state=True)
        with closing(connect(run/'raw.sqlite')) as conn:
            crawl(rpc,conn,start,end,args.chunk)
            events,liqs=normalize(rpc,conn,start,end,run/'processed',ts(args.start),ts(args.end))
        activity_candidates(events,run/'processed')
        hourly_oracle_prices(rpc,start,end,run/'processed')
        manifest['event_counts']=dict(Counter(e['protocol']+':'+e['event_type'] for e in events))
        manifest['total_events']=len(events); manifest['liquidation_related_logs']=len(liqs)
        save_json(run/'manifest.json',manifest)
        if not args.skip_snapshot:
            positions,validations=snapshot(rpc,events,start-1,args.max_wallets,run/'processed',args.wallet_file)
            stress(positions,run/'processed')
            manifest['snapshot_validations']=dict(Counter(v['status'] for v in validations))
        if not args.skip_valuations:
            valued=enrich_liquidations(rpc,liqs,run/'processed'); concentration(valued,run/'processed')
        if args.receipts: manifest['receipts_sampled']=receipt_flows(rpc,events,args.receipts,run/'processed')
        manifest['rq_readiness']={
            'RQ1':'Validated Aave non-E-mode wallet SAMPLE only; no full-universe claim',
            'RQ2':'Aave valued concentration if enabled; other protocol logs separate',
            'RQ3':'Transfer sample only; swaps/traces/history and negative-control cohort still required',
            'RQ4':'Complete counts for selected contracts/window; longer history and price controls required',
            'RQ5':'Cross-protocol events only; no exposure network or causal transmission claim'}
        manifest['status']='completed'
    except Exception as exc:
        manifest['status']='failed'; manifest['error']=type(exc).__name__+': '+str(exc)
        raise
    finally:
        manifest['finished_utc']=datetime.now(timezone.utc).isoformat()
        manifest['rpc_requests']=rpc.requests; manifest['cache_hits']=rpc.hits
        manifest['outputs']={str(p.relative_to(run)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (run/'processed').glob('*.csv')}
        manifest['source_hashes']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'data/sources').glob('*.sol')}
        save_json(run/'manifest.json',manifest)
        print(f'Run {args.run_id}: {manifest["status"]}',flush=True)

if __name__=='__main__':
    try:main()
    except RpcError as exc:raise SystemExit(f'CRAWL STOPPED [{exc.kind}]: {exc}')
