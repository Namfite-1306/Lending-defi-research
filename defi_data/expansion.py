"""A–E research expansion. Raw RPC evidence, resumable coverage, strict readiness gates."""
import argparse, csv, hashlib, json, time, sqlite3
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from decimal import Decimal as D
from .rpc import Rpc,RpcError
from .evm import addr, uint, words, topic, parse_events, decode_event, address_array
from .pipeline import ROOT, CONTRACTS, PROVIDER, ZERO, ts, utc, save_json, csv_write, connect, call, call_request, registry, metadata, base_row

RUN=ROOT/'data/runs/expansion_20260930'
PILOT=ROOT/'data/runs/stress_20250203_smoke/processed'
OUT=RUN/'processed'
START='2023-01-27T00:00:00Z'; END='2026-10-01T00:00:00Z'

def read_csv(path):
    if not path.exists(): return []
    with path.open(encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))

def history(workers=3,minutes=20,chunk=50000):
    RUN.mkdir(parents=True,exist_ok=True); OUT.mkdir(exist_ok=True)
    rpc=Rpc(ROOT/'data/rpc_cache')
    bounds=RUN/'block_range.json'
    if not bounds.exists():
        head=int(rpc.one('eth_blockNumber',[],cache=False),16)-64
        start=rpc.block_at(ts(START),head); end=rpc.block_at(ts(END),head)-1
        save_json(bounds,{'start_block':start,'end_block':end,'start_utc':START,'end_exclusive_utc':END,
                         'start_hash':rpc.block(start)['hash'],'end_hash':rpc.block(end)['hash']})
    b=json.loads(bounds.read_text()); start,end=b['start_block'],b['end_block']
    rpc.preflight(start,end,RUN/'rpc_preflight_history.json')
    conn=connect(RUN/'raw.sqlite'); conn.execute('PRAGMA journal_mode=WAL')
    # Protocol-specific histories; empty predeployment ranges remain evidence of absence, never exposures.
    specs={}; jobs=[]
    for p,(a,source,names) in CONTRACTS.items():
        allspec=parse_events((ROOT/'data/sources'/source).read_text())
        specs[p]={allspec[n]['topic']:(n,allspec[n]) for n in names}
        for lo in range(start,end+1,chunk):
            hi=min(lo+chunk-1,end)
            if not conn.execute('SELECT 1 FROM coverage WHERE protocol=? AND start=? AND end=?',(p,lo,hi)).fetchone():
                jobs.append((p,a,lo,hi))
    # Interleave protocols chronologically; a failure must not hide the other protocols.
    jobs.sort(key=lambda j:(j[2],j[0])); deadline=time.monotonic()+minutes*60
    failures=[]; completed=0;consecutive_failures=0;halt=False
    def fetch(job):
        p,a,lo,hi=job
        r=Rpc(ROOT/'data/rpc_cache',urls=rpc.urls)
        logs=r.logs(a,list(specs[p]),lo,hi)
        values=[]
        for log in logs:
            if log.get('removed'): raise ValueError('Removed log')
            name,spec=specs[p][log['topics'][0]]
            values.append((1,log['transactionHash'],int(log['logIndex'],16),int(log['blockNumber'],16),
                           log['blockHash'],p,name,json.dumps(log),json.dumps(decode_event(log,spec))))
        return job,values,r.block(lo)['hash'],r.block(hi)['hash']
    # Bounded submission: checkpoints are committed before scheduling more work.
    with ThreadPoolExecutor(max_workers=workers) as pool:
        it=iter(jobs); pending={}
        for _ in range(workers):
            job=next(it,None)
            if job: pending[pool.submit(fetch,job)]=job
        while pending:
            f=next(as_completed(pending)); job=pending.pop(f)
            try:
                (p,a,lo,hi),values,lh,hh=f.result()
                with conn:
                    conn.executemany('INSERT OR REPLACE INTO logs VALUES (?,?,?,?,?,?,?,?,?)',values)
                    conn.execute('INSERT OR REPLACE INTO coverage VALUES (?,?,?,?,?)',(p,lo,hi,lh,hh))
                completed+=1
                consecutive_failures=0
                print(f'HISTORY {p} {lo}-{hi}: {len(values)} logs; {completed}/{len(jobs)} remaining chunks',flush=True)
            except Exception as e:
                consecutive_failures+=1
                halt=halt or getattr(e,'kind',None) in ('history_unavailable','authorization','invalid_response') or consecutive_failures>=3
                failures.append({'protocol':job[0],'start':job[2],'end':job[3],'error':str(e)[:500]})
                print(f'HISTORY failed {job[0]} {job[2]}: {str(e)[:180]}',flush=True)
            if not halt and time.monotonic()<deadline:
                job=next(it,None)
                if job: pending[pool.submit(fetch,job)]=job
    save_json(RUN/'history_attempt.json',{'at_utc':utc(int(time.time())),'new_chunks':completed,'failures':failures,
              'requested_minutes':minutes,'complete':False})
    conn.close(); export_history()
    if failures:raise RpcError(f'{len(failures)} history chunks failed; checkpoints retained, history remains unverified.',kind='partial_history')

def export_history():
    b=json.loads((RUN/'block_range.json').read_text()); lo,hi=b['start_block'],b['end_block']
    conn=connect(RUN/'raw.sqlite'); summaries=[]; borrowers={}; coverage=[]
    for p in CONTRACTS:
        ranges=list(conn.execute('SELECT start,end FROM coverage WHERE protocol=? ORDER BY start',(p,)))
        blocks=sum(y-x+1 for x,y in ranges)
        counts=dict(conn.execute('SELECT name,count(*) FROM logs WHERE protocol=? GROUP BY name',(p,)))
        coverage.append({'protocol':p,'target_start_block':lo,'target_end_block':hi,'covered_blocks':blocks,
                         'target_blocks':hi-lo+1,'coverage_fraction':blocks/(hi-lo+1),'complete':False,
                         'verified_coverage_fraction':0,'quality_gate':'quarantined: unexpectedly empty historical responses; independent receipt reconciliation required',
                         'event_counts':json.dumps(counts),'scope':'selected contract and event signatures only'})
        gaps=[]; cursor=lo
        for x,y in ranges:
            if x>cursor:gaps.append((cursor,x-1))
            cursor=max(cursor,y+1)
        if cursor<=hi:gaps.append((cursor,hi))
        for x,y in gaps:summaries.append({'protocol':p,'missing_from_block':x,'missing_to_block':y,'blocks':y-x+1})
    for block,raw,decoded in conn.execute("SELECT block,raw,decoded FROM logs WHERE protocol='aave_v3' AND name='Borrow' ORDER BY block,idx"):
        d=json.loads(decoded); a=d['onBehalfOf']
        if a not in borrowers:borrowers[a]={'account':a,'first_observed_borrow_block':block,'source_tx':json.loads(raw)['transactionHash'],
                                         'universe_complete':all(r['complete'] for r in coverage if r['protocol']=='aave_v3'),
                                         'selection':'Borrow events observed on or before snapshot; not future liquidation membership'}
    csv_write(OUT/'history_coverage.csv',coverage); csv_write(OUT/'history_gaps.csv',summaries)
    csv_write(OUT/'borrower_universe.csv',list(borrowers.values()))
    conn.close()

def signed(word):
    n=uint(word);return n-(1<<256) if n>=1<<255 else n

def protocol_hf(collateral,weighted,debt,base,revision=0):
    if not debt:return None
    if revision>=9:
        # Aave Ethereum Pool revision 9 (v3.5) onward: preserve the weighted
        # threshold until AFTER wadDiv; do not truncate average LT first.
        numerator=int(weighted*base*10000);denominator=int(debt*base)
        return D(((numerator*10**18+denominator//2)//denominator)//10000)/10**18
    average_lt=int(weighted*10000/collateral) if collateral else 0
    c=int(collateral*base);d=int(debt*base)
    adjusted=(c*average_lt+5000)//10000
    return D((adjusted*10**18+d//2)//d)/10**18

def risk_debt_raw(stable,scaled_variable,index,revision):
    ray=10**27
    return stable+(scaled_variable*index+(ray-1 if revision>=9 else ray//2))//ray

def extended_window():
    OUT.mkdir(parents=True,exist_ok=True)
    save_json(OUT/'extended_window_gate.json',{'passed':False,'status':'not_completed; requires successful crawl and sentinel validation'})
    pilot_events=read_csv(PILOT/'events.csv')
    expected={(e['tx_hash'],int(e['log_index'])) for e in pilot_events
              if e['protocol']=='aave_v3' and e['event_type'] in ('Borrow','Supply')}
    if not expected:raise RpcError('Missing validated pilot Borrow/Supply sentinel. Supply stress_20250203_smoke/processed/events.csv before expansion window; an empty sentinel must not pass validation.',kind='missing_input')
    rpc=Rpc(ROOT/'data/rpc_cache');pool=CONTRACTS['aave_v3'][0]
    specs=parse_events((ROOT/'data/sources/IPool.sol').read_text());bytopic={specs[n]['topic']:(n,specs[n]) for n in ('Borrow','Supply')}
    head=int(rpc.one('eth_blockNumber',[],cache=False),16)-64
    begin=rpc.block_at(ts('2025-02-01T00:00:00Z'),head);end=rpc.block_at(ts('2025-02-06T00:00:00Z'),head)-1
    rpc.preflight(begin,end,RUN/'rpc_preflight_window.json')
    logs=[]
    for lo in range(begin,end+1,1000):
        data=rpc.logs(pool,list(bytopic),lo,min(lo+999,end));logs+=data
        print(f'C extended {lo}: {len(data)} logs',flush=True)
    # Sentinel: this query must contain every Borrow/Supply in the already validated pilot.
    actual={(l['transactionHash'],int(l['logIndex'],16)) for l in logs}
    if not expected.issubset(actual):
        save_json(OUT/'extended_window_gate.json',{'passed':False,'expected_pilot_keys':len(expected),'missing_pilot_keys':len(expected-actual),
                    'raw_logs_returned':len(logs),'status':'quarantined; provider range responses omit known logs'})
        return
    blocks=sorted({int(l['blockNumber'],16) for l in logs})
    if logs and all(l.get('blockTimestamp') for l in logs):
        times={int(l['blockNumber'],16):int(l['blockTimestamp'],16) for l in logs}
        hashes={int(l['blockNumber'],16):l['blockHash'] for l in logs}
        check_blocks=sorted(set(blocks[::max(1,len(blocks)//24)]+blocks[-1:]))
        headers=rpc.many([('eth_getBlockByNumber',[hex(b),False]) for b in check_blocks])
        for b,h in zip(check_blocks,headers):
            if int(h['timestamp'],16)!=times[b] or h['hash']!=hashes[b]:raise ValueError('Log timestamp/header mismatch')
        for l in logs:
            if int(l['blockTimestamp'],16)!=times[int(l['blockNumber'],16)]:raise ValueError('Inconsistent timestamp within block')
    else:
        headers=rpc.many([('eth_getBlockByNumber',[hex(b),False]) for b in blocks]);times={b:int(h['timestamp'],16) for b,h in zip(blocks,headers)}
    events=[]
    for l in logs:
        name,spec=bytopic[l['topics'][0]];d=decode_event(l,spec)
        r=base_row(('aave_v3',name,l),d,times[int(l['blockNumber'],16)])
        r.update(account=d['onBehalfOf'],token_address=d['reserve']);events.append(r)
    csv_write(OUT/'recursive_extended_events.csv',events)
    candidates=[];sensitivity=[];window_end=ts('2025-02-06T00:00:00Z')
    for h in (6,24,48):
        c=window_candidates(events,h,window_end);candidates+=c
        eligible=sum(e['event_type']=='Borrow' and ts(e['timestamp_utc'])+h*3600<=window_end for e in events)
        sensitivity.append({'window_hours':h,'candidate_motifs':len(c),'uncensored_borrow_starts':eligible,
                            'verified_recursive_labels':0,'status':'motifs only; swap funding attribution pending'})
    csv_write(OUT/'recursive_window_candidates.csv',candidates);csv_write(OUT/'recursive_window_sensitivity.csv',sensitivity)
    save_json(OUT/'extended_window_gate.json',{'passed':True,'events':len(events),'start_utc':'2025-02-01T00:00:00Z',
              'end_exclusive_utc':'2025-02-06T00:00:00Z','pilot_keys_reconciled':len(expected),
              'timestamp_source':'RPC blockTimestamp, checked against headers' if logs and all(l.get('blockTimestamp') for l in logs) else 'block headers',
              'header_checks':len(headers),'unique_blocks':len(blocks)})

def enrich():
    OUT.mkdir(parents=True,exist_ok=True); rpc=Rpc(ROOT/'data/rpc_cache')
    events=read_csv(PILOT/'events.csv')
    # Independent pre-event lookback discovers borrowers without using future liquidations.
    cutoff=21762264; begin=cutoff-7200
    rpc.preflight(begin,cutoff,RUN/'rpc_preflight_enrich.json',require_state=True)
    pool=CONTRACTS['aave_v3'][0]; spec=parse_events((ROOT/'data/sources/IPool.sol').read_text())['Borrow']
    prior=rpc.logs(pool,[spec['topic']],begin,cutoff)
    wallets=sorted({decode_event(l,spec)['onBehalfOf'] for l in prior})
    csv_write(OUT/'pre_snapshot_borrower_cohort.csv',[{'account':a,'discovered_from_block':begin,'information_cutoff_block':cutoff,
                'selection':'prior Borrow events only','full_universe':False} for a in wallets])
    # Validate a deterministic sample including E-mode, independent of subsequent liquidation outcome.
    modes=rpc.many([call_request(pool,'getUserEMode(address)',[a],cutoff) for a in wallets])
    pairs=list(zip(wallets,[uint(words(x)[0]) for x in modes]))
    selected=[x for x in pairs if x[1]][:6]+[x for x in pairs if not x[1]][:6]
    aave_positions(rpc,cutoff,selected)
    flows_and_windows(rpc,events)
    cross_protocol(rpc,events,cutoff)
    versions(rpc)
    save_json(RUN/'enrichment_status.json',{'finished_utc':utc(int(time.time())),'source_window':'pilot + 7200-block prior Borrow lookback',
              'borrowers_in_prior_window':len(wallets),'snapshots_selected':len(selected),'full_history_ready':False})

def versions(rpc):
    # EIP-1967 implementation slot; hashes distinguish upgrades even under one proxy address.
    slot='0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc'
    bounds=json.loads((RUN/'block_range.json').read_text())
    rpc.preflight(bounds['start_block'],bounds['end_block'],RUN/'rpc_preflight_versions.json',require_state=True)
    points=sorted(set([bounds['start_block'],17000000,19000000,21762264,24000000,bounds['end_block']]))
    rows=[]
    for b in points:
        pool,oracle,provider=registry(rpc,b)
        implementation=addr(rpc.one('eth_getStorageAt',[pool,slot,hex(b)]))
        code=rpc.one('eth_getCode',[implementation,hex(b)])
        rows.append({'block_number':b,'timestamp_utc':utc(int(rpc.block(b)['timestamp'],16)),'pool':pool,'oracle':oracle,
                     'data_provider':provider,'implementation':implementation,'code_sha256':hashlib.sha256(bytes.fromhex(code[2:])).hexdigest(),
                     'coverage':'selected checkpoints, not complete upgrade/configuration timeline'})
    csv_write(OUT/'protocol_versions_sample.csv',rows)

def aave_positions(rpc,b,selected):
    pool,oracle,provider=registry(rpc,b)
    revision=uint(call(rpc,pool,'POOL_REVISION()',[],b)[0])
    if not 1<=revision<=11:raise ValueError('Unreviewed Pool revision; add explicit adapter')
    reserves=address_array(rpc.one(*call_request(pool,'getReservesList()',[],b)))
    meta=metadata(rpc,reserves,b); base=D(uint(call(rpc,oracle,'BASE_CURRENCY_UNIT()',[],b)[0]))
    cfg=rpc.many([call_request(provider,'getReserveConfigurationData(address)',[t],b) for t in reserves])
    rawcfg=rpc.many([call_request(pool,'getConfiguration(address)',[t],b) for t in reserves])
    reserve_data=rpc.many([call_request(pool,'getReserveData(address)',[t],b) for t in reserves])
    prices=rpc.many([call_request(oracle,'getAssetPrice(address)',[t],b) for t in reserves])
    indexes=rpc.many([call_request(pool,'getReserveNormalizedVariableDebt(address)',[t],b) for t in reserves])
    rows=[];checks=[];configs=[];categories=[]
    for t,c,raw,rd,p,ind in zip(reserves,cfg,rawcfg,reserve_data,prices,indexes):
        w=words(c); rw=uint(words(raw)[0]); data=words(rd)
        meta[t].update(price=D(uint(words(p)[0]))/base,lt=D(uint(w[2]))/10000,category=(rw>>168)&255,reserve_id=uint(data[7]),debt_index=uint(words(ind)[0]))
        configs.append({'block_number':b,'token_address':t,**meta[t],'ltv':str(D(uint(w[1]))/10000),
                        'liquidation_bonus_factor':str(D(uint(w[3]))/10000),'configuration_word':str(rw),
                        'historical_source':'eth_call at explicit block; no latest-state substitution'})
    for a,mode in selected:
        cat=None
        if mode:
            # Explicit 2025 ABI: ltv,threshold,bonus,priceSource,label offset. Reject unknown layouts.
            raw=rpc.one(*call_request(pool,'getEModeCategoryData(uint8)',[mode],b)); w=words(raw)
            if uint(w[0])!=32 or len(w)<7: raise ValueError('Unsupported E-mode tuple layout')
            w=w[1:] # dynamic tuple return has an outer ABI offset
            bitmap_result=rpc.many([call_request(pool,'getEModeCategoryCollateralBitmap(uint8)',[mode],b)],allow_errors=True)[0]
            bitmap=None if isinstance(bitmap_result,dict) else uint(words(bitmap_result)[0])
            cat={'mode':mode,'lt':D(uint(w[1]))/10000,'price_source':addr(w[3]),'block':b,
                 'collateral_bitmap':str(bitmap) if bitmap is not None else '',
                 'abi':'legacy getter plus category bitmap' if bitmap is not None else 'legacy reserve category'}
            categories.append(cat)
            if cat['price_source']!=ZERO: raise ValueError('Custom category price source requires explicit pricing adapter')
        balances=rpc.many([call_request(provider,'getUserReserveData(address,address)',[t,a],b) for t in reserves])
        total_c=D(0);total_d=D(0);weighted=D(0);local=[]
        for t,result in zip(reserves,balances):
            w=words(result)
            if len(w)!=9:raise ValueError('Unsupported historical provider ABI')
            s=uint(w[0]);repay=uint(w[1])+uint(w[2]);enabled=bool(uint(w[8]));m=meta[t]
            d=risk_debt_raw(uint(w[1]),uint(w[4]),m['debt_index'],revision)
            if not s and not d:continue
            eligible=bool(int(cat['collateral_bitmap']) & (1<<m['reserve_id'])) if cat and cat['collateral_bitmap']!='' else bool(cat and m['category']==mode)
            lt=cat['lt'] if eligible else m['lt']
            oracle_raw=int(m['price']*base)
            unit=10**m['decimals']
            cv=D(s*oracle_raw//unit)/base if enabled and (m['lt']>0 or revision>=10) else D(0)
            dv=D((d*oracle_raw+(unit-1 if revision>=9 else 0))//unit)/base;total_c+=cv;total_d+=dv;weighted+=cv*lt
            local.append({'account':a,'block_number':b,'token_address':t,'symbol':m['symbol'],'supply_raw':str(s),'debt_raw':str(d),
                          'collateral_enabled':enabled,'emode':mode,'effective_liquidation_threshold':str(lt),
                          'collateral_usd':str(cv),'debt_usd':str(dv),'price_usd':str(m['price']),
                          'selection':'pre_snapshot_borrow_history_sample','pool_revision':revision,
                          'repayable_debt_raw':str(repay),'hf_debt_raw':str(d)})
        account=call(rpc,pool,'getUserAccountData(address)',[a],b)
        c=D(uint(account[0]))/base;d=D(uint(account[1]))/base
        hf=D(uint(account[5]))/10**18 if d else None; calc=protocol_hf(total_c,weighted,total_d,base,revision)
        errors=[abs(c-total_c)/max(c,D(1)),abs(d-total_d)/max(d,D(1))]
        if hf is not None and calc is not None:errors.append(abs(hf-calc)/max(hf,D(1)))
        ok=max(errors)<=D('.0001')
        checks.append({'account':a,'block_number':b,'emode':mode,'reported_debt_usd':str(d),'hf_reported':str(hf),
                       'hf_calculated':str(calc),'max_relative_error':str(max(errors)),'passed':ok,'scope':'sample only','pool_revision':revision})
        for r in local:r['validation_passed']=ok
        rows+=local
        print(f'B snapshot mode={mode} pass={ok} tokens={len(local)}',flush=True)
    csv_write(OUT/'historical_reserve_config_sample.csv',configs)
    csv_write(OUT/'emode_categories_sample.csv',categories)
    csv_write(OUT/'positions_point_in_time_sample.csv',rows);csv_write(OUT/'position_checks.csv',checks)
    save_json(OUT/'position_scope.json',{'block':b,'pool':pool,'oracle':oracle,'provider':provider,'full_universe':False,
              'supported_abi':'version-aware Pool revisions 1–11; each snapshot requires HF reconciliation; later revisions fail closed',
              'snapshots_are':'block-end state; not pre-transaction state for intra-block events'})

def window_candidates(events,hours,end_stamp):
    grouped=defaultdict(list);out=[]
    for e in events:
        if e['protocol']=='aave_v3' and e.get('account'):grouped[e['account']].append(e)
    for a,es in grouped.items():
        es.sort(key=lambda e:(int(e['block_number']),int(e['transaction_index']),int(e['log_index'])))
        for i,borrow in enumerate(es):
            if borrow['event_type']!='Borrow':continue
            stamp=ts(borrow['timestamp_utc']); censor=stamp+hours*3600>end_stamp
            found=False
            for j in range(i+1,len(es)):
                supply=es[j]
                if ts(supply['timestamp_utc'])-stamp>hours*3600:break
                if supply['event_type']!='Supply':continue
                for reb in es[j+1:]:
                    if ts(reb['timestamp_utc'])-stamp>hours*3600:break
                    if reb['event_type']=='Borrow' and reb['token_address']==borrow['token_address']:
                        out.append({'account':a,'window_hours':hours,'borrow_tx':borrow['tx_hash'],'supply_tx':supply['tx_hash'],
                          'reborrow_tx':reb['tx_hash'],'borrow_token':borrow['token_address'],'supply_token':supply['token_address'],
                          'label_available_at':reb['timestamp_utc'],'right_censored':censor,'verified_recursive':False,
                          'interpretation':'temporal motif; swap funding and ownership not proven'})
                        found=True
                        break
                if found:break
    return out

def flows_and_windows(rpc,events):
    candidates=[]
    for h in (6,24,48):candidates+=window_candidates(events,h,ts('2025-02-03T03:00:00Z'))
    gate_path=OUT/'extended_window_gate.json'
    extended_ready=gate_path.exists() and json.loads(gate_path.read_text()).get('passed',False)
    if not extended_ready:
        csv_write(OUT/'recursive_window_candidates.csv',candidates)
        csv_write(OUT/'recursive_window_sensitivity.csv',[{'window_hours':h,'candidate_motifs':sum(r['window_hours']==h for r in candidates),
            'uncensored_borrow_starts':0,'verified_recursive_labels':0,'status':'3-hour input cannot evaluate 6/24/48-hour negatives'} for h in (6,24,48)])
    # Liquidation execution receipts plus all motif transactions, deterministic cap reported.
    hashes=list(dict.fromkeys([e['tx_hash'] for e in events if e['event_type']=='LiquidationCall']))[:40]
    hashes+=list(dict.fromkeys(r[k] for r in candidates for k in ('borrow_tx','supply_tx','reborrow_tx') if r[k] not in hashes))[:40]
    receipts=rpc.many([('eth_getTransactionReceipt',[h]) for h in hashes])
    v2=topic('Swap(address,uint256,uint256,uint256,uint256,address)')
    v3=topic('Swap(address,address,int256,int256,uint160,uint128,int24)')
    swaps=[];gas=[];pools={};liquidity=[];errors=[]
    for r in receipts:
        b=int(r['blockNumber'],16);price=int(r.get('effectiveGasPrice','0x0'),16);used=int(r['gasUsed'],16)
        gas.append({'tx_hash':r['transactionHash'],'block_number':b,'gas_used':used,'effective_gas_price_wei':str(price),
                    'gas_cost_eth':str(D(used*price)/10**18),'status':int(r['status'],16),
                    'omits':'builder payments and off-chain hedging; receipt gas is not total strategy cost'})
        for l in r['logs']:
            if not l['topics'] or l['topics'][0] not in (v2,v3):continue
            w=words(l['data']);kind='v2' if l['topics'][0]==v2 else 'v3'
            if len(w)!=(4 if kind=='v2' else 5):continue
            pool=l['address'].lower();pools[(pool,b,kind)]=True
            swaps.append({'tx_hash':r['transactionHash'],'block_number':b,'log_index':int(l['logIndex'],16),'pool':pool,'pool_type':kind,
                          'amounts_raw':json.dumps([uint(x) for x in w[:4]] if kind=='v2' else [signed(w[0]),signed(w[1])]),
                          'source':'Swap signature; factory verification required','attribution':'not automatically collateral sale by liquidator'})
    for pool,b,kind in list(pools)[:30]:
        try:
            tokens=[addr(call(rpc,pool,sig,[],b)[0]) for sig in ('token0()','token1()')]
            factory=addr(call(rpc,pool,'factory()',[],b)[0])
            if kind=='v2':state=call(rpc,pool,'getReserves()',[],b-1)
            else:state=call(rpc,pool,'slot0()',[],b-1)+call(rpc,pool,'liquidity()',[],b-1)
            liquidity.append({'pool':pool,'block_number':b-1,'type':kind,'token0':tokens[0],'token1':tokens[1],'factory':factory,
                              'pre_block_state_words':json.dumps([uint(w) for w in state]),
                              'state_timing':'previous block end; not exact pre-swap state','curve_ready':kind=='v2',
                              'limitation':'V3 needs initialized tick liquidity; observed pool set is selected sample'})
        except Exception as e:errors.append({'pool':pool,'block':b,'error':str(e)[:300]})
    # Factory attribution is separate from a matching event signature.
    known={'0x1f98431c8ad98523631ae4a59f267346ea31f984':'Uniswap V3',
           '0x5c69bee701ef814a2b6a3edd4b1652cb9cc5aa6f':'Uniswap V2',
           '0xc0aee478e3658e2610c5f7a4a2e1777ce9e4f2ac':'Sushi V2'}
    bypool={r['pool']:r for r in liquidity}
    for r in swaps:
        lp=bypool.get(r['pool'])
        if not lp:continue
        r['factory_label']=known.get(lp['factory'],'unverified factory')
        r['token0']=lp['token0'];r['token1']=lp['token1']
        try:
            m=metadata(rpc,[lp['token0'],lp['token1']],r['block_number'])
            amounts=json.loads(r['amounts_raw'])
            if r['pool_type']=='v3':a0,a1=abs(amounts[0]),abs(amounts[1])
            else:a0,a1=amounts[0]+amounts[2],amounts[1]+amounts[3]
            q0=D(a0)/10**m[lp['token0']]['decimals'];q1=D(a1)/10**m[lp['token1']]['decimals']
            r['token0_quantity']=str(q0);r['token1_quantity']=str(q1)
            r['execution_token1_per_token0']=str(q1/q0) if q0 else ''
        except Exception as e:errors.append({'pool':r['pool'],'stage':'swap units','error':str(e)[:300]})
    csv_write(OUT/'execution_gas_sample.csv',gas);csv_write(OUT/'dex_swaps_sample.csv',swaps)
    csv_write(OUT/'dex_liquidity_sample.csv',liquidity);save_json(OUT/'dex_failures.json',errors)

def cross_protocol(rpc,events,b):
    comet=CONTRACTS['compound_v3_usdc'][0];morpho=CONTRACTS['morpho_blue'][0]
    assets=[];rows=[];markets=[];errors=[]
    n=uint(call(rpc,comet,'numAssets()',[],b)[0]);base=addr(call(rpc,comet,'baseToken()',[],b)[0])
    for i in range(n):
        w=call(rpc,comet,'getAssetInfo(uint8)',[i],b)
        assets.append({'protocol':'compound_v3_usdc','block':b,'offset':uint(w[0]),'token':addr(w[1]),'price_feed':addr(w[2]),
                       'scale':str(uint(w[3])),'borrow_collateral_factor':str(D(uint(w[4]))/10**18),
                       'liquidate_collateral_factor':str(D(uint(w[5]))/10**18),'liquidation_factor':str(D(uint(w[6]))/10**18)})
    # Point-in-time position calls, not event activity interpreted as balances.
    wallets=sorted({e['account'] for e in events if e['protocol']=='compound_v3_usdc' and e.get('account')})[:8]
    for a in wallets:
        try:
            debt=uint(call(rpc,comet,'borrowBalanceOf(address)',[a],b)[0])
            rows.append({'protocol':'compound_v3_usdc','block':b,'account':a,'market_id':comet,'token':base,'kind':'debt','amount_raw':str(debt),
                         'scope':'pilot activity-selected sample; not unbiased cohort'})
            for x in assets:
                bal=uint(call(rpc,comet,'collateralBalanceOf(address,address)',[a,x['token']],b)[0])
                if bal:rows.append({'protocol':'compound_v3_usdc','block':b,'account':a,'market_id':comet,'token':x['token'],
                                   'kind':'collateral','amount_raw':str(bal),'scope':'pilot activity-selected sample'})
        except Exception as e:errors.append({'protocol':'compound_v3_usdc','account':a,'error':str(e)[:300]})
    ids=sorted({e['market_id'] for e in events if e['protocol']=='morpho_blue'})
    for mid in ids:
        try:
            p=call(rpc,morpho,'idToMarketParams(bytes32)',[mid],b);state=call(rpc,morpho,'market(bytes32)',[mid],b)
            markets.append({'market_id':mid,'block':b,'loan_token':addr(p[0]),'collateral_token':addr(p[1]),'oracle':addr(p[2]),
                            'irm':addr(p[3]),'lltv':str(D(uint(p[4]))/10**18),'market_state_raw':json.dumps([uint(x) for x in state]),
                            'debt_conversion_status':'stored totals; accrue interest + virtual shares + rounding required before valuation'})
            users=sorted({e['account'] for e in events if e['protocol']=='morpho_blue' and e['market_id']==mid and e.get('account')})[:2]
            for a in users:
                w=call(rpc,morpho,'position(bytes32,address)',[mid,a],b)
                rows.append({'protocol':'morpho_blue','block':b,'account':a,'market_id':mid,'token':addr(p[0]),'kind':'borrow_shares',
                             'amount_raw':str(uint(w[1])),'scope':'shares are not loan-token amounts'})
                rows.append({'protocol':'morpho_blue','block':b,'account':a,'market_id':mid,'token':addr(p[1]),'kind':'collateral',
                             'amount_raw':str(uint(w[2])),'scope':'market-specific point-in-time collateral'})
        except Exception as e:errors.append({'protocol':'morpho_blue','market':mid,'error':str(e)[:300]})
    csv_write(OUT/'compound_asset_configs.csv',assets);csv_write(OUT/'morpho_market_configs.csv',markets)
    csv_write(OUT/'cross_protocol_position_sample.csv',rows);save_json(OUT/'cross_protocol_failures.json',errors)

def main():
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['history','enrich','export','window','versions','flows']);p.add_argument('--minutes',type=int,default=20)
    p.add_argument('--workers',type=int,default=3);p.add_argument('--chunk',type=int,default=50000);a=p.parse_args()
    if a.phase=='history':history(a.workers,a.minutes,a.chunk)
    elif a.phase=='enrich':enrich()
    elif a.phase=='window':extended_window()
    elif a.phase=='versions':versions(Rpc(ROOT/'data/rpc_cache'))
    elif a.phase=='flows':flows_and_windows(Rpc(ROOT/'data/rpc_cache'),read_csv(PILOT/'events.csv'))
    else:export_history()
if __name__=='__main__':
    try:main()
    except RpcError as exc:
        save_json(RUN/'crawl_failure.json',{'status':'failed','kind':exc.kind,'error':str(exc),'at_utc':utc(int(time.time()))})
        raise SystemExit(f'CRAWL STOPPED [{exc.kind}]: {exc}')
