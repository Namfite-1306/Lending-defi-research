"""Three distinct data audits: structural, independent on-chain, research suitability."""
import argparse,csv,json,hashlib,zlib,time,calendar,os
from collections import Counter,defaultdict
from datetime import datetime,timezone
from decimal import Decimal as D
from .recovery import RUN,OUT,OLD,database,export,merge_ranges,http
from .pipeline import ROOT,CONTRACTS,csv_write,save_json,ts,utc,call
from .expansion import read_csv
from .evm import parse_events,decode_event,words,uint,calldata
from .rpc import Rpc,DEFAULT_RPC_URLS

def record(check,passed,detail,severity='integrity'):
    return {'check':check,'passed':bool(passed),'severity':severity,'detail':detail}

def pass1(models=None):
    OUT.mkdir(parents=True,exist_ok=True);export();c=database();checks=[]
    integrity=c.execute('PRAGMA integrity_check').fetchone()[0]
    checks.append(record('SQLite integrity',integrity=='ok',integrity))
    coverage=read_csv(OUT/'history_coverage.csv')
    checks.append(record('Full target block coverage',all(r['download_complete']=='True' for r in coverage),coverage))
    specs={}
    for p,(_,source,names) in CONTRACTS.items():
        s=parse_events((ROOT/'data/sources'/source).read_text(encoding='utf8'));specs[p]={s[n]['topic']:(n,s[n]) for n in names}
    invalid=[];count=0;digest=hashlib.sha256();bounds=json.loads((RUN/'block_range.json').read_text(encoding='utf8'))
    # Exhaustive raw/decoded/key/schema consistency. Streams from SQLite, not a RAM sample.
    for p,b,txi,i,tx,h,stamp,name,a,token,market,d,raw in c.execute('SELECT * FROM events'):
        count+=1
        try:
            l=json.loads(zlib.decompress(raw));n,s=specs[p][l['topics'][0]]
            actual=decode_event(l,s)
            ok=(n==name and actual==json.loads(d) and l['transactionHash']==tx and int(l['logIndex'],16)==i
                and int(l['blockNumber'],16)==b and l['blockHash']==h and l['address'].lower()==CONTRACTS[p][0]
                and bounds['start_block']<=b<=bounds['end_block'] and not l.get('removed'))
            if l.get('blockTimestamp'):ok=ok and int(l['blockTimestamp'],16)==stamp
            if not ok:invalid.append({'tx':tx,'idx':i,'reason':'stored/raw/decoded mismatch'})
            digest.update(f'{p}|{tx}|{i}|{h}|{stamp}|{d}\n'.encode())
        except Exception as e:invalid.append({'tx':tx,'idx':i,'reason':str(e)[:200]})
        if count%250000==0:print(f'AUDIT1 checked {count:,} raw records',flush=True)
    checks.append(record('Exhaustive raw decode and identity',not invalid,{'records':count,'invalid_count':len(invalid),'examples':invalid[:20],'physical_scan_sha256':digest.hexdigest()}))
    # Shards may overlap after resume with a different chunk size. Union coverage,
    # not SUM(length), is authoritative; each shard's event keys must still match.
    c.execute('CREATE INDEX IF NOT EXISTS recovery_protocol_block ON events(protocol,block)');c.commit()
    mismatches=[]
    for p,lo,hi,n,dig,fh,lh in c.execute('SELECT * FROM ranges').fetchall():
        keys=sorted(c.execute('SELECT tx,idx FROM events WHERE protocol=? AND block BETWEEN ? AND ?',(p,lo,hi)))
        actual=hashlib.sha256(json.dumps(keys).encode()).hexdigest()
        if len(keys)!=n or actual!=dig:mismatches.append({'protocol':p,'lo':lo,'hi':hi,'stored_count':n,'actual_count':len(keys)})
    checks.append(record('Shard keys/counts reconcile after dedup',not mismatches,{'mismatches':mismatches[:30],'count':len(mismatches)}))
    result={'at_utc':utc(int(time.time())),'checks':checks,'records':count,'all_integrity_passed':all(x['passed'] for x in checks)}
    if models is not None:result['models']=models
    save_json(RUN/'audit_1_structure.json',result)
    c.close()

def pass2(models=None):
    c=database();checks=[];samples=[];rpc=Rpc(RUN/'independent_audit_cache',urls=os.getenv('ETH_AUDIT_RPC_URLS','https://eth-mainnet.public.blastapi.io'),batch_size=10,multicall=True)
    if models is not None:
        primary={s.strip().rstrip('/') for s in os.getenv('ETH_RPC_URLS',','.join(DEFAULT_RPC_URLS)).split(',') if s.strip()}
        separate=not primary.intersection(u.rstrip('/') for u in rpc.urls)
        checks.append(record('Audit endpoint differs from collection endpoint',separate,{'separate_endpoints':separate,'note':'Different endpoints alone do not prove independent infrastructure'}))
    prior=read_csv(OUT/'independent_onchain_samples.csv') if (OUT/'independent_onchain_samples.csv').exists() else []
    good={(r['protocol'],int(r['year']),int(r['quarter_month'])):r for r in prior if r['log_keys_match']=='True' and r['receipt_match']=='True'}
    c.execute('CREATE INDEX IF NOT EXISTS recovery_protocol_stamp ON events(protocol,stamp)');c.commit()
    for p in (['aave_v3'] if models is not None else CONTRACTS):
        for year in range(2023,2027):
            for month in (1,4,7,10):
                begin=calendar.timegm((year,month,1,0,0,0));last=calendar.timegm((year+(month==10),(month+3-1)%12+1,1,0,0,0))
                if begin>=ts('2026-10-01T00:00:00Z'):continue
                anchor=c.execute('SELECT block,tx,idx,hash FROM events WHERE protocol=? AND stamp>=? AND stamp<? ORDER BY stamp LIMIT 1',(p,begin,last)).fetchone()
                if not anchor:continue
                b,tx,i,h=anchor;entry={'protocol':p,'year':year,'quarter_month':month,'block':b,'tx':tx}
                if models is None and (p,year,month) in good:
                    entry=good[p,year,month];entry.update(log_keys_match=True,receipt_match=True)
                    samples.append(entry);continue
                try:
                    # Fresh independent request: ≤5 blocks respects this provider's 10-block cap.
                    spec=parse_events((ROOT/'data/sources'/CONTRACTS[p][1]).read_text(encoding='utf8'))
                    topics=[spec[n]['topic'] for n in CONTRACTS[p][2]]
                    logs=rpc.one('eth_getLogs',[{'address':CONTRACTS[p][0],'topics':[topics],'fromBlock':hex(b),'toBlock':hex(b+4)}],cache=False)
                    received={(l['transactionHash'],int(l['logIndex'],16)) for l in logs}
                    stored=set(c.execute('SELECT tx,idx FROM events WHERE protocol=? AND block BETWEEN ? AND ?',(p,b,b+4)))
                    receipt=rpc.one('eth_getTransactionReceipt',[tx],cache=False)
                    receipt_match=receipt['blockHash']==h and any(int(l['logIndex'],16)==i and l['address'].lower()==CONTRACTS[p][0] for l in receipt['logs'])
                    entry.update(log_keys_match=received==stored,receipt_match=receipt_match,independent_count=len(received),stored_count=len(stored))
                except Exception as e:entry.update(log_keys_match=False,receipt_match=False,error=str(e)[:400])
                samples.append(entry);print(f'AUDIT2 {p} {year}-{month}: {entry.get("log_keys_match")}',flush=True)
    checks.append(record('Quarterly independent log/receipt checks',bool(samples) and all(r['log_keys_match'] and r['receipt_match'] for r in samples),{'samples':len(samples),'mismatches':sum(not r['log_keys_match'] or not r['receipt_match'] for r in samples)}))
    if models is not None:
        if 1 in models:
            validation=read_csv(RUN/'full_snapshot_21762264/validation.csv')
            chosen=validation[::max(1,len(validation)//5)][:5];fresh=[]
            for row in chosen:
                try:
                    value=rpc.one('eth_call',[{'to':CONTRACTS['aave_v3'][0],'data':calldata('getUserAccountData(address)',row['account'])},hex(21762264)],cache=False)
                    w=words(value);debt=D(uint(w[1]))/10**8;hf=D(uint(w[5]))/10**18
                    passed=(abs(debt-D(row['debt_reported_usd']))/max(debt,D(1))<=D('.0001') and abs(hf-D(row['hf_reported']))/max(hf,D(1))<=D('.0001'))
                    fresh.append({'account':row['account'],'passed':passed})
                except Exception as exc:fresh.append({'account':row['account'],'passed':False,'error':rpc._safe_message(exc)})
            checks.append(record('Independent full-snapshot account samples',bool(fresh) and all(r['passed'] for r in fresh),fresh))
        csv_write(OUT/'independent_onchain_samples.csv',samples)
        save_json(RUN/'audit_2_onchain.json',{'at_utc':utc(int(time.time())),'models':models,'checks':checks,'all_integrity_passed':all(x['passed'] for x in checks)})
        c.close();return
    accrual=read_csv(OUT/'morpho_accrual_validation.csv')
    checks.append(record('Morpho accrual matches transient on-chain execution',len(accrual)==52 and all(r['all_six_market_fields_match']=='True' for r in accrual),{'markets':len(accrual)}))
    snapshot=[]
    for path in (RUN/'snapshots').glob('*/position_checks.csv'):snapshot+=read_csv(path)
    checks.append(record('Version-aware position/HF validation',bool(snapshot) and all(r['passed']=='True' for r in snapshot),
       {'wallet_snapshots':len(snapshot),'blocks':len({r['block_number'] for r in snapshot}),'failed':sum(r['passed']!='True' for r in snapshot),
        'max_relative_error':max((r['max_relative_error'] for r in snapshot),key=D,default='n.a.')}))
    replay=read_csv(OUT/'v3_swap_replay_validation.csv');eligible=[r for r in replay if r.get('eligible')=='True']
    checks.append(record('Exact swap replay on eligible first pool touches',bool(eligible) and all(r.get('exact_replay_match')=='True' for r in eligible),
        {'eligible':len(eligible),'excluded_intra_block_or_errors':len(replay)-len(eligible),'matched':sum(r.get('exact_replay_match')=='True' for r in eligible)}))
    csv_write(OUT/'independent_onchain_samples.csv',samples)
    save_json(RUN/'audit_2_onchain.json',{'at_utc':utc(int(time.time())),'checks':checks,'all_integrity_passed':all(x['passed'] for x in checks)})
    c.close()

def pass3(models=None):
    if models is not None:return scoped_research_audit(models)
    c=database();checks=[];prices=read_csv(OUT/'market_prices_hourly_full_period.csv');groups=defaultdict(list)
    print('AUDIT3 hourly price grid loaded',flush=True)
    for r in prices:groups[r['feed']].append(r)
    expected=(ts('2026-10-01T00:00:00Z')-ts('2023-01-27T00:00:00Z'))//3600
    nofuture=all(not r['source_update_utc'] or ts(r['source_update_utc'])<=ts(r['timestamp_utc']) for r in prices)
    missing=sum(not r['price_usd'] for r in prices);stale=sum(r['stale']=='True' for r in prices)
    checks.append(record('Price controls: full hourly grid, no future alignment',{'ETH/USD','BTC/USD'}.issubset(groups) and all(len(r)==expected for r in groups.values()) and nofuture and missing==0,
        {'expected_per_feed':expected,'actual_rows':len(prices),'missing':missing,'stale_over_2h':stale,'stale_policy':'exclude stale rows or sensitivity; never convert missing prices to zero'}))
    universe=read_csv(OUT/'borrower_universe.csv');actual=c.execute("SELECT count(DISTINCT account) FROM events NOT INDEXED WHERE protocol='aave_v3' AND name='Borrow'").fetchone()[0]
    print('AUDIT3 borrower universe reconciled',flush=True)
    checks.append(record('Borrower Universe reconciles with full Borrow history',len(universe)==actual and bool(universe) and all(r['history_complete']=='True' for r in universe),{'exported':len(universe),'distinct_onchain_borrowers':actual}))
    # Full negative/control labels are only available after horizon; positive evidence
    # is available at reborrow time. Do not apply end-of-window labels to prior snapshots.
    candidates=OUT/'recursive_candidates_full_history.csv';bad=0;n=0;censored=0
    if candidates.exists():
        with candidates.open(encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                n+=1;bad+=ts(r['label_available_at'])<int(r['borrow_stamp']);censored+=r['right_censored']=='True'
    checks.append(record('Recursive labels retain availability and censoring',candidates.exists() and bad==0,{'candidate_rows':n,'invalid_availability':bad,'censored':censored}))
    print('AUDIT3 recursive labels checked',flush=True)
    flow=read_csv(OUT/'recursive_receipt_verification.csv');verified=sum(r['status'].startswith('verified') for r in flow)
    checks.append(record('Funding-verified positive examples available',verified>0,{'receipts_examined':len(flow),'verified':verified,'unresolved_are_not_negative':True,'representative_cohort_validation_complete':False},'readiness'))
    full=json.loads((RUN/'full_snapshot_21762264/scope.json').read_text(encoding='utf8'))
    checks.append(record('Full pre-stress Aave snapshot reconciles',full.get('full_snapshot_complete') and full.get('passed')==full.get('active_debt_wallets') and full.get('active_debt_wallets',0)>0,full))
    exposures=read_csv(OUT/'exposures_valued_sample.csv');unknown=sum(r['priced']!='True' and r.get('value_usd')!='0' for r in exposures)
    checks.append(record('Full-market multi-date positions/exposure universe',False,{'sample_exposure_rows':len(exposures),'unpriced_rows':unknown,
        'reason':'balances verified on sampled cohorts; not all borrowers at all model dates'},'readiness'))
    checks.append(record('Cascade and policy calibration across full liquidation waves',False,{'reason':'exact single-pool replay is available, but full routes/intra-block states, external funding and full exposure replay are not complete'},'readiness'))
    # Freeze every processed CSV plus raw DB identity as research provenance.
    inventory=[]
    paths=list(OUT.glob('*.csv'))+list((RUN/'full_snapshot_21762264').glob('*.csv'))+list((RUN/'snapshots').glob('*/*.csv'))
    for path in sorted(paths):
        h=hashlib.sha256();rows=-1;columns=0
        with path.open(encoding='utf-8-sig',newline='') as f:
            reader=csv.reader(f)
            for row in reader:
                if rows==-1:columns=len(row)
                rows+=1
        with path.open('rb') as f:
            for chunk in iter(lambda:f.read(8*1024*1024),b''):h.update(chunk)
        inventory.append({'file':str(path.relative_to(RUN)),'rows':max(0,rows),'columns':columns,'sha256':h.hexdigest(),'path':str(path)})
    save_json(RUN/'freeze_manifest.json',{'at_utc':utc(int(time.time())),'csv_files':inventory,'raw_database':str(RUN/'history.sqlite'),
                'readiness_is_distinct_from_integrity':True})
    save_json(RUN/'audit_3_research.json',{'at_utc':utc(int(time.time())),'checks':checks,
        'all_integrity_passed':all(x['passed'] for x in checks if x['severity']=='integrity'),
        'all_readiness_passed':all(x['passed'] for x in checks if x['severity']=='readiness')})
    c.close()

def scoped_research_audit(models):
    """Audit RQ1/RQ4 inputs without certifying unrelated models or sample universes."""
    from defi_models.core import Data,DEFAULTS,sha
    checks=[];inventory=[]
    for path in sorted(list(OUT.glob('*.csv'))+list((RUN/'full_snapshot_21762264').glob('*.csv'))):
        inventory.append({'file':str(path.relative_to(RUN)),'sha256':sha(path)})
    save_json(RUN/'freeze_manifest.json',{'at_utc':utc(int(time.time())),'models':models,'csv_files':inventory,'raw_database':str(RUN/'history.sqlite')})
    data=Data(RUN,dict(DEFAULTS))
    for n,suffix in [(1,'structure'),(2,'onchain')]:
        path=RUN/f'audit_{n}_{suffix}.json'
        prior=json.loads(path.read_text(encoding='utf8')) if path.exists() else {}
        checks.append(record(f'Audit {n} passed for selected models',prior.get('all_integrity_passed') and set(models).issubset(prior.get('models',range(1,8))),{}))
    if 1 in models:
        try:
            _,scope=data.snapshot()
            checks.append(record('Full pre-stress snapshot and baseline HF reconcile',scope.get('borrower_history_complete'),scope))
        except (ValueError,OSError,KeyError,TypeError) as exc:checks.append(record('Full pre-stress snapshot and baseline HF reconcile',False,str(exc)))
    if 4 in models:
        try:
            from defi_models.core import stamp
            bounds=json.loads((RUN/'block_range.json').read_text(encoding='utf8'))
            first=ts(bounds['start_utc']);last=ts(bounds['end_exclusive_utc']);expected=list(range(first,last,3600))
            counts=[r for r in data.read('liquidations_hourly_full_period.csv') if r['protocol']=='aave_v3']
            prices=data.read('market_prices_hourly_full_period.csv');events=[r for r in data.read('liquidations_model_table.csv') if r['protocol']=='aave_v3']
            prices_ok=True
            for feed in ['ETH/USD','BTC/USD']:
                rows=sorted((r for r in prices if r['feed']==feed),key=lambda r:r['timestamp_utc'])
                prices_ok=prices_ok and [stamp(r['timestamp_utc']) for r in rows]==expected and all(D(r['price_usd'])>0 and stamp(r['source_update_utc'])<=stamp(r['timestamp_utc']) and stamp(r.get('source_available_utc') or r['source_update_utc'])<=stamp(r['timestamp_utc']) for r in rows)
            checks.append(record('ETH/BTC full hourly grid, positive prices and no future alignment',prices_ok,{'expected_hours':len(expected)}))
            actual=Counter(int(stamp(r['timestamp_utc']))//3600 for r in events)
            counts=sorted(counts,key=lambda r:r['hour_utc'])
            panel_ok=([stamp(r['hour_utc']) for r in counts]==expected and len({(r['tx'],r['logidx']) for r in events})==len(events) and all(int(r['liquidation_events'])==actual[int(stamp(r['hour_utc']))//3600] for r in counts if r['protocol_deployed']=='True') and all(first<=stamp(r['timestamp_utc'])<last for r in events))
            checks.append(record('Liquidation events and full hourly panel reconcile',panel_ok,{'events':len(events),'hours':len(counts)}))
        except (ValueError,OSError,KeyError,TypeError,ArithmeticError) as exc:checks.append(record('RQ4 complete tables and alignment',False,str(exc)))
    result={'at_utc':utc(int(time.time())),'models':models,'checks':checks,'all_integrity_passed':all(x['passed'] for x in checks),'scope':'Only selected RQ1/RQ4 inputs; other models are not certified'}
    save_json(RUN/'audit_3_research.json',result)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('round',choices=['1','2','3']);p.add_argument('--models',nargs='+',type=int,choices=[1,4]);a=p.parse_args()
    {'1':pass1,'2':pass2,'3':pass3}[a.round](a.models)
