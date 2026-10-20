"""Research data recovery, independent endpoint probes and explicit three-pass audits."""
import argparse,csv,hashlib,json,time,urllib.request,urllib.error,sqlite3
import zlib
import gzip
import threading
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
from collections import Counter,defaultdict
from decimal import Decimal as D
from .pipeline import ROOT,CONTRACTS,PROVIDER,call,call_request,registry,metadata,csv_write,save_json,utc
from .expansion import read_csv,signed,window_candidates
from .rpc import Rpc,RpcError
from .evm import parse_events,decode_event,words,uint,addr,topic,calldata,keccak

RUN=ROOT/'data/runs/recovery_20261020';OUT=RUN/'processed';OLD=ROOT/'data/runs/expansion_20260930'
URLS=['https://eth-mainnet.public.blastapi.io','https://rpc.flashbots.net','https://ethereum-rpc.publicnode.com',
      'https://ethereum.publicnode.com','https://eth.llamarpc.com','https://1rpc.io/eth',
      'https://rpc.mevblocker.io','https://eth.drpc.org','https://eth-mainnet.public.blastapi.io']

def http(url,method,params):
    payload={'jsonrpc':'2.0','id':1,'method':method,'params':params}
    req=urllib.request.Request(url,json.dumps(payload).encode(),{'Content-Type':'application/json','User-Agent':'DeFiResearch/2.0','Accept-Encoding':'gzip'})
    try:
        with urllib.request.urlopen(req,timeout=40) as f:
            body=f.read();r=json.loads(gzip.decompress(body) if f.headers.get('Content-Encoding')=='gzip' else body)
        if 'error' in r:raise RpcError(str(r['error']))
        if 'result' not in r or r['result'] is None:raise RpcError('missing result')
        return r['result']
    except urllib.error.HTTPError as e:raise RpcError(f'HTTP {e.code}: '+e.read(250).decode(errors='replace'))

def diagnose():
    OUT.mkdir(parents=True,exist_ok=True)
    spec=parse_events((ROOT/'data/sources/IPool.sol').read_text(encoding='utf8'))['Borrow']
    pool=CONTRACTS['aave_v3'][0]
    def probe(pair):
        i,url=pair;result={'provider_id':i,'checks':[]}
        for lo,hi in [(16550000,16550999),(19000000,19000999),(21762265,21762275)]:
            entry={'start':lo,'end':hi}
            try:
                logs=http(url,'eth_getLogs',[{'address':pool,'topics':[spec['topic']],'fromBlock':hex(lo),'toBlock':hex(hi)}])
                entry.update(count=len(logs),sample_tx=logs[0]['transactionHash'] if logs else None)
                if logs:
                    receipt=http(url,'eth_getTransactionReceipt',[logs[0]['transactionHash']])
                    entry['receipt_match']=any(l['address'].lower()==pool and l['logIndex']==logs[0]['logIndex'] for l in receipt['logs'])
            except Exception as e:entry['error']=str(e)[:300]
            result['checks'].append(entry)
            print(f'provider {i}: {lo}: {entry.get("count",entry.get("error"))}',flush=True)
        return result
    with ThreadPoolExecutor(max_workers=4) as ex:results=list(ex.map(probe,enumerate(URLS)))
    save_json(RUN/'rpc_diagnosis.json',results)

def scope_probe():
    OUT.mkdir(parents=True,exist_ok=True);pool=CONTRACTS['aave_v3'][0]
    specs=parse_events((ROOT/'data/sources/IPool.sol').read_text(encoding='utf8'))
    url='https://rpc.mevblocker.io';results=[]
    for lo in [16494436,16544436,16644436,18000000,19000000,24000000,26080000]:
        entry={'start':lo,'end':lo+9999}
        try:
            logs=http(url,'eth_getLogs',[{'address':pool,'fromBlock':hex(lo),'toBlock':hex(lo+9999),
                                         'topics':[[specs[n]['topic'] for n in CONTRACTS['aave_v3'][2]]]}])
            entry.update(count=len(logs),sample_tx=logs[0]['transactionHash'] if logs else None)
            if logs:
                r=http(url,'eth_getTransactionReceipt',[logs[0]['transactionHash']]);entry['receipt_match']=any(l['logIndex']==logs[0]['logIndex'] and l['address'].lower()==pool for l in r['logs'])
            print(entry,flush=True)
        except Exception as e:entry['error']=str(e)[:400];print(entry,flush=True)
        results.append(entry)
    save_json(RUN/'scope_probe.json',results)

def database():
    RUN.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(RUN/'history.sqlite',timeout=60)
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('CREATE TABLE IF NOT EXISTS events (protocol TEXT,block INTEGER,txidx INTEGER,idx INTEGER,tx TEXT,hash TEXT,stamp INTEGER,name TEXT,account TEXT,token TEXT,market TEXT,decoded TEXT,raw BLOB,PRIMARY KEY(tx,idx))')
    c.execute('CREATE TABLE IF NOT EXISTS ranges (protocol TEXT,lo INTEGER,hi INTEGER,count INTEGER,digest TEXT,first_hash TEXT,last_hash TEXT,PRIMARY KEY(protocol,lo,hi))')
    c.execute('CREATE TABLE IF NOT EXISTS failures (protocol TEXT,lo INTEGER,hi INTEGER,error TEXT,attempt_utc TEXT)')
    return c

def full_history(workers=4,chunk=50000):
    OUT.mkdir(parents=True,exist_ok=True)
    b=json.loads((OLD/'block_range.json').read_text(encoding='utf8'));start,end=b['start_block'],b['end_block']
    save_json(RUN/'block_range.json',b)
    c=database();specs={};jobs=[];url='https://rpc.mevblocker.io'
    for p,(a,source,names) in CONTRACTS.items():
        s=parse_events((ROOT/'data/sources'/source).read_text(encoding='utf8'));specs[p]={s[n]['topic']:(n,s[n]) for n in names}
        existing=merge_ranges(list(c.execute('SELECT lo,hi FROM ranges WHERE protocol=?',(p,))))
        for lo in range(start,end+1,chunk):
            hi=min(lo+chunk-1,end)
            if not any(x<=lo and y>=hi for x,y in existing):jobs.append((p,a,lo,hi))
    # Interleave early and late periods so live progress covers the target rather than one prefix.
    jobs.sort(key=lambda j:(j[2],j[0]));ordered=[]
    left,right=0,len(jobs)-1
    while left<=right:
        ordered.append(jobs[left]);left+=1
        if left<=right:ordered.append(jobs[right]);right-=1
    throttle=threading.Lock();next_request=[0.0]
    def getlogs(p,a,lo,hi):
        for attempt in range(5):
            with throttle:
                wait=max(0,next_request[0]-time.monotonic());next_request[0]=max(time.monotonic(),next_request[0])+.65
            if wait:time.sleep(wait)
            try:
                result=http(url,'eth_getLogs',[{'address':a,'topics':[list(specs[p])],'fromBlock':hex(lo),'toBlock':hex(hi)}])
                # Guard silent result caps as well as explicit size errors.
                if len(result) in (1000,2000,5000,10000,20000,32768,50000,65536,100000) and hi>lo:
                    mid=(lo+hi)//2;return getlogs(p,a,lo,mid)+getlogs(p,a,mid+1,hi)
                return result
            except Exception as e:
                msg=str(e).lower()
                if (any(x in msg for x in ('range','too many','limit exceeded','response size')) or
                    (any(x in msg for x in ('temporarily unavailable','timed out')) and hi-lo>500)) and hi>lo:
                    mid=(lo+hi)//2;return getlogs(p,a,lo,mid)+getlogs(p,a,mid+1,hi)
                if any(x in msg for x in ('pruned','personal token')):raise
                if '429' in msg:
                    with throttle:next_request[0]=max(next_request[0],time.monotonic()+30)
                if attempt==4:raise
                time.sleep(min(8,2**attempt))
    def fetch(job):
        p,a,lo,hi=job;logs=getlogs(p,a,lo,hi);rows=[]
        keys=set()
        for l in logs:
            if l.get('removed'):raise ValueError('Removed log')
            bn=int(l['blockNumber'],16)
            if not lo<=bn<=hi or l['address'].lower()!=a:raise ValueError('Range/address mismatch')
            key=(l['transactionHash'],int(l['logIndex'],16))
            if key in keys:raise ValueError('Duplicate RPC log')
            keys.add(key);name,s=specs[p][l['topics'][0]];d=decode_event(l,s)
            account=d.get('onBehalfOf',d.get('onBehalf',d.get('borrower',d.get('user',d.get('dst',d.get('src',''))))))
            stamp=int(l['blockTimestamp'],16) if l.get('blockTimestamp') else int(http(url,'eth_getBlockByNumber',[hex(bn),False])['timestamp'],16)
            rows.append((p,bn,int(l['transactionIndex'],16),key[1],key[0],l['blockHash'],stamp,name,account,d.get('reserve',d.get('asset','')),d.get('id',a),json.dumps(d,separators=(',',':')),
                         zlib.compress(json.dumps(l,separators=(',',':')).encode(),3)))
        # Hashes of first/last emitted logs; target boundaries are pinned separately.
        # Avoid two redundant header requests per shard (thousands over full history).
        lh=logs[0]['blockHash'] if logs else '';hh=logs[-1]['blockHash'] if logs else ''
        digest=hashlib.sha256(json.dumps(sorted(keys)).encode()).hexdigest()
        return rows,digest,lh,hh
    completed=0;failures=0;total=len(ordered)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        it=iter(ordered);pending={}
        for _ in range(workers):
            j=next(it,None)
            if j:pending[ex.submit(fetch,j)]=j
        while pending:
            f=next(as_completed(pending));j=pending.pop(f);p,a,lo,hi=j
            try:
                rows,digest,lh,hh=f.result()
                with c:
                    c.executemany('INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',rows)
                    c.execute('INSERT OR REPLACE INTO ranges VALUES (?,?,?,?,?,?,?)',(p,lo,hi,len(rows),digest,lh,hh))
                completed+=1
                if completed%10==0 or completed<5:print(f'HISTORY {completed}/{total}; {p} {lo}-{hi}: {len(rows)} records; failures={failures}',flush=True)
            except Exception as e:
                failures+=1
                with c:c.execute('INSERT INTO failures VALUES (?,?,?,?,?)',(p,lo,hi,str(e)[:500],utc(int(time.time()))))
                print(f'HISTORY failure {p} {lo}: {str(e)[:150]}',flush=True)
            save_json(RUN/'progress.json',{'completed_this_run':completed,'jobs_this_run':total,'failures_this_run':failures,'at_utc':utc(int(time.time()))})
            j=next(it,None)
            if j:pending[ex.submit(fetch,j)]=j
    c.close();export()

def merge_ranges(ranges):
    merged=[]
    for a,b in sorted(ranges):
        if merged and a<=merged[-1][1]+1:merged[-1][1]=max(b,merged[-1][1])
        else:merged.append([a,b])
    return merged

WAD=10**18
def accrued_market(state,rate,stamp):
    s=list(state);elapsed=stamp-s[4]
    if elapsed<0:raise ValueError('Future lastUpdate')
    first=rate*elapsed;second=first*first//(2*WAD);third=second*first//(3*WAD)
    interest=s[2]*(first+second+third)//WAD
    s[0]+=interest;s[2]+=interest
    if s[5]:
        fee=interest*s[5]//WAD
        s[1]+=fee*(s[1]+10**6)//(s[0]-fee+1)
    s[4]=stamp
    return s

def to_assets_up(shares,assets,total_shares):
    return (shares*(assets+1)+total_shares+10**6-1)//(total_shares+10**6)

def simulated_accrual(rpc,morpho,params,mid,b):
    # Read-only eth_call: temporary helper executes accrueInterest and reads market
    # in ONE simulation. All writes are discarded by the node. No signed tx.
    helper='0x00000000000000000000000000000000deadbeef'
    code='0x60a460006000376000600060a46000600073'+morpho[2:]+'5af161020052602460a460003760c06101006024600073'+morpho[2:]+'5afa61022052610140610100f3'
    data=calldata('accrueInterest((address,address,address,address,uint256))',*params)+calldata('market(bytes32)',mid)[2:]
    result=rpc.one('eth_call',[{'to':helper,'data':data,'gas':hex(8000000)},hex(b),{helper:{'code':code}}])
    w=words(result)
    if len(w)!=10 or uint(w[8])!=1 or uint(w[9])!=1:raise ValueError('Accrual simulation failed')
    return [uint(x) for x in w[:6]]

def repair_exposures():
    OUT.mkdir(parents=True,exist_ok=True)
    rpc=Rpc(ROOT/'data/rpc_cache',batch_size=10);b=21762264
    morpho=CONTRACTS['morpho_blue'][0];comet=CONTRACTS['compound_v3_usdc'][0]
    positions=read_csv(OLD/'processed/cross_protocol_position_sample.csv')
    configs=read_csv(OLD/'processed/morpho_market_configs.csv')
    assets={r['token']:r for r in read_csv(OLD/'processed/compound_asset_configs.csv')}
    pool,oracle,provider=registry(rpc,b);base=uint(call(rpc,oracle,'BASE_CURRENCY_UNIT()',[],b)[0]);stamp=int(rpc.block(b)['timestamp'],16)
    loan_tokens=sorted({r['loan_token'] for r in configs}|{r['token'] for r in positions if r['protocol']=='compound_v3_usdc'})
    metas=metadata(rpc,loan_tokens,b)
    prices=rpc.many([call_request(oracle,'getAssetPrice(address)',[t],b) for t in loan_tokens],allow_errors=True)
    usd={t:(D(uint(words(x)[0]))/base if isinstance(x,str) and uint(words(x)[0]) else None) for t,x in zip(loan_tokens,prices)}
    acc=[];exposures=[];errors=[];market_states={}
    for conf in configs:
        mid=conf['market_id'];state=json.loads(conf['market_state_raw'])
        params=[conf['loan_token'],conf['collateral_token'],conf['oracle'],conf['irm'],int(D(conf['lltv'])*WAD)]
        try:
            rate=0 if conf['irm']=='0x'+'0'*40 else uint(call(rpc,conf['irm'],
                'borrowRateView((address,address,address,address,uint256),(uint128,uint128,uint128,uint128,uint128,uint128))',params+state,b)[0])
            calculated=accrued_market(state,rate,stamp)
            # IRM==0 only changes lastUpdate; formula above has zero interest.
            simulated=simulated_accrual(rpc,morpho,params,mid,b)
            matched=calculated==simulated
            acc.append({'market_id':mid,'block':b,'elapsed_seconds':stamp-state[4],'borrow_rate_per_second_wad':str(rate),
                        'calculated_total_borrow_assets':str(calculated[2]),'simulated_total_borrow_assets':str(simulated[2]),
                        'all_six_market_fields_match':matched,'source':'eth_call transient accrueInterest + market, no transaction'})
            if not matched:raise ValueError('Accrual does not match simulation')
            op=0 if conf['oracle']=='0x'+'0'*40 else uint(call(rpc,conf['oracle'],'price()',[],b)[0])
            market_states[mid]=(conf,calculated,op)
            print(f'E accrual {len(acc)}/{len(configs)} match={matched}',flush=True)
        except Exception as e:errors.append({'market_id':mid,'stage':'accrual','error':str(e)[:400]})
    for r in positions:
        try:
            token=r['token'];raw=int(r['amount_raw']);p=r['protocol'];kind=r['kind'];mid=r['market_id']
            if p=='morpho_blue':
                if mid not in market_states:continue
                conf,s,op=market_states[mid];loan=conf['loan_token'];price=usd.get(loan)
                debt=to_assets_up(raw,s[2],s[3]) if kind=='borrow_shares' else None
                amount=D(debt if debt is not None else raw*op//10**36)/10**metas[loan]['decimals']
                value=amount*price if price is not None else None
                actual_kind='debt' if kind=='borrow_shares' else 'collateral'
                extra={'borrow_shares_raw':str(raw) if debt is not None else '',
                       'loan_equivalent_raw':str(debt if debt is not None else raw*op//10**36),'valuation_token':loan}
            else:
                feed=addr(call(rpc,comet,'baseTokenPriceFeed()',[],b)[0]) if kind=='debt' else assets[token]['price_feed']
                price=D(uint(call(rpc,comet,'getPrice(address)',[feed],b)[0]))/10**8
                value=D(raw)/10**metas[token]['decimals']*price;actual_kind=kind;extra={}
            exposures.append({'protocol':p,'account':r['account'],'market_id':mid,'block':b,'asset':token,'kind':actual_kind,
                              'value_usd':str(value) if value is not None else '', 'priced':value is not None,
                              'scope':'activity-selected validation cohort; not full universe',**extra})
        except Exception as e:errors.append({'account':r['account'],'market_id':r['market_id'],'stage':'valuation','error':str(e)[:300]})
    for r in read_csv(OLD/'processed/positions_point_in_time_sample.csv'):
        for kind,col in [('collateral','collateral_usd'),('debt','debt_usd')]:
            if D(r[col])>0:exposures.append({'protocol':'aave_v3','account':r['account'],'market_id':pool,'block':b,
                'asset':r['token_address'],'kind':kind,'value_usd':r[col],'priced':True,'scope':'prior-borrow sampled cohort'})
    csv_write(OUT/'morpho_accrual_validation.csv',acc);csv_write(OUT/'exposures_valued_sample.csv',exposures)
    save_json(RUN/'exposure_errors.json',errors)
    # Typed bipartite edges: wallet -> market -> asset, never alleged ownership/causality.
    csv_write(OUT/'exposure_network_edges.csv',[{'source':'wallet:'+r['account'],'target':r['protocol']+':'+r['market_id'],
        'asset':r['asset'],'edge_type':r['kind'],'usd':r['value_usd'],'block':b,'causal_claim':False}
        for r in exposures if r['priced'] and D(r['value_usd'])>0])

def configuration_history():
    OUT.mkdir(parents=True,exist_ok=True);rpc=Rpc(ROOT/'data/rpc_cache',batch_size=5)
    bounds=json.loads((OLD/'block_range.json').read_text(encoding='utf8'));lo,hi=bounds['start_block'],bounds['end_block']
    conf=addr(call(rpc,PROVIDER,'getPoolConfigurator()',[],hi)[0]);pool=CONTRACTS['aave_v3'][0]
    source_url='https://raw.githubusercontent.com/aave-dao/aave-v3-origin/main/src/contracts/interfaces/IPoolConfigurator.sol'
    source=urllib.request.urlopen(source_url,timeout=30).read().decode();(RUN/'IPoolConfigurator.sol').write_text(source,encoding='utf8')
    specs=parse_events(source);bytopic={s['topic']:(n,s) for n,s in specs.items()}
    rows=[];coverage=[];rawfile=RUN/'configuration_logs.jsonl'
    # Sparse events: large intervals are safe if endpoint accepts them; split on explicit range error.
    def logs(a,x,y,topics=None):
        filt={'address':a,'fromBlock':hex(x),'toBlock':hex(y)}
        if topics:filt['topics']=[topics]
        try:return http('https://rpc.mevblocker.io','eth_getLogs',[filt])
        except Exception as e:
            if (any(t in str(e).lower() for t in ('range','too many','limit','response size','temporarily unavailable')) or y-x>100000) and y>x:
                mid=(x+y)//2;return logs(a,x,mid,topics)+logs(a,mid+1,y,topics)
            raise
    raw=[]
    for name,a,topics in [('provider',PROVIDER,None),('configurator',conf,None),('pool_upgrade',pool,[topic('Upgraded(address)')])]:
        data=logs(a,lo,hi,topics);raw+=data
        coverage.append({'contract_role':name,'address':a,'lo':lo,'hi':hi,'logs':len(data),'extraction_complete':True})
        for l in data:
            t=l['topics'][0];label='unparsed_event';decoded={}
            if name=='configurator' and t in bytopic:
                label,s=bytopic[t]
                try:decoded=decode_event(l,s)
                except Exception:label='ABI_mismatch:'+label
            elif name=='pool_upgrade':label='Upgraded';decoded={'implementation':addr(l['topics'][1])}
            rows.append({'contract_role':name,'address':a,'block':int(l['blockNumber'],16),'tx':l['transactionHash'],
                         'txidx':int(l['transactionIndex'],16),'logidx':int(l['logIndex'],16),'topic0':t,
                         'event':label,'decoded':json.dumps(decoded),'source':'on-chain configuration event; raw retained'})
        print(f'B config {name}: {len(data)} logs',flush=True)
    rawfile.write_text(''.join(json.dumps(l)+'\n' for l in raw),encoding='utf8')
    csv_write(OUT/'configuration_timeline.csv',sorted(rows,key=lambda r:(r['block'],r['txidx'],r['logidx'])))
    csv_write(OUT/'configuration_coverage.csv',coverage)
    save_json(RUN/'configuration_source.json',{'url':source_url,'sha256':hashlib.sha256(source.encode()).hexdigest(),
                 'limitation':'unparsed/dynamic events retained raw; constants close factor require implementation source mapping'})

def snapshots_by_version():
    from . import expansion
    timeline=read_csv(OUT/'configuration_timeline.csv');bounds=json.loads((OLD/'block_range.json').read_text(encoding='utf8'))
    points=sorted(set([17000000,19000000,21762264,bounds['end_block']]+[int(r['block'])+600 for r in timeline if r['event']=='Upgraded' and int(r['block'])+600<=bounds['end_block']]))
    rpc=Rpc(ROOT/'data/rpc_cache',batch_size=25,multicall=True);c=database();pool=CONTRACTS['aave_v3'][0];summary=[]
    for b in points:
        folder=RUN/'snapshots'/str(b);folder.mkdir(parents=True,exist_ok=True)
        if (folder/'position_checks.csv').exists():
            check=read_csv(folder/'position_checks.csv')
            if check and all(r['passed']=='True' and 'pool_revision' in r for r in check):
                summary.append({'block':b,'wallets':len(check),'passed':len(check),'status':'completed'});continue
        # All selected addresses have an observed borrow BEFORE this cutoff.
        wallets=[r[0] for r in c.execute("SELECT account FROM events WHERE protocol='aave_v3' AND name='Borrow' AND block<=? GROUP BY account ORDER BY max(block) DESC LIMIT 80",(b,))]
        if not wallets:summary.append({'block':b,'wallets':0,'passed':0,'status':'no prior borrowers in currently downloaded history'});continue
        accounts=rpc.many([call_request(pool,'getUserAccountData(address)',[a],b) for a in wallets],allow_errors=True)
        active=[a for a,r in zip(wallets,accounts) if isinstance(r,str) and len(words(r))>=6 and uint(words(r)[1])>0]
        modes=rpc.many([call_request(pool,'getUserEMode(address)',[a],b) for a in active],allow_errors=True)
        pairs=[(a,uint(words(r)[0])) for a,r in zip(active,modes) if isinstance(r,str)]
        selected=[x for x in pairs if x[1]][:1]+[x for x in pairs if not x[1]][:1]
        previous=expansion.OUT;expansion.OUT=folder
        try:
            if selected:
                expansion.aave_positions(rpc,b,selected)
                check=read_csv(folder/'position_checks.csv');summary.append({'block':b,'wallets':len(check),'passed':sum(r['passed']=='True' for r in check),'status':'completed'})
            else:summary.append({'block':b,'wallets':0,'passed':0,'status':'no active wallets in deterministic sample'})
        except Exception as e:summary.append({'block':b,'wallets':len(selected),'passed':0,'status':str(e)[:400]})
        finally:expansion.OUT=previous
        csv_write(OUT/'snapshot_version_validation.csv',summary)
        print(f'B version snapshot {b}: {summary[-1]}',flush=True)
    csv_write(OUT/'snapshot_version_validation.csv',summary);c.close()

def export():
    c=database();b=json.loads((RUN/'block_range.json').read_text(encoding='utf8'));start,end=b['start_block'],b['end_block']
    coverage=[];gaps=[]
    for p in CONTRACTS:
        ranges=merge_ranges(list(c.execute('SELECT lo,hi FROM ranges WHERE protocol=?',(p,))))
        covered=sum(y-x+1 for x,y in ranges);n=c.execute('SELECT count(*) FROM events WHERE protocol=?',(p,)).fetchone()[0]
        coverage.append({'protocol':p,'covered_blocks':covered,'target_blocks':end-start+1,'fraction':covered/(end-start+1),
                         'download_complete':covered==end-start+1,'records':n,'validation':'three-pass audit required'})
        cursor=start
        for a,z in ranges:
            if a>cursor:gaps.append({'protocol':p,'lo':cursor,'hi':a-1})
            cursor=max(cursor,z+1)
        if cursor<=end:gaps.append({'protocol':p,'lo':cursor,'hi':end})
    csv_write(OUT/'history_coverage.csv',coverage);csv_write(OUT/'history_gaps.csv',gaps, ['protocol','lo','hi'])
    universe=[]
    for a,first,last,n in c.execute("SELECT account,min(block),max(block),count(*) FROM events WHERE protocol='aave_v3' AND name='Borrow' GROUP BY account"):
        universe.append({'account':a,'first_borrow_block':first,'last_borrow_block':last,'borrow_count':n,'history_complete':coverage[0]['download_complete']})
    csv_write(OUT/'borrower_universe.csv',universe,['account','first_borrow_block','last_borrow_block','borrow_count','history_complete'])
    csv_write(OUT/'event_counts.csv',[{'protocol':p,'event':n,'count':count} for p,n,count in c.execute('SELECT protocol,name,count(*) FROM events GROUP BY protocol,name')])
    c.close();print(json.dumps(coverage),flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['diagnose','probe','history','export','exposures','configs','snapshots']);p.add_argument('--workers',type=int,default=4);p.add_argument('--chunk',type=int,default=50000);a=p.parse_args()
    if a.phase=='diagnose':diagnose()
    elif a.phase=='probe':scope_probe()
    elif a.phase=='history':full_history(a.workers,a.chunk)
    elif a.phase=='exposures':repair_exposures()
    elif a.phase=='configs':configuration_history()
    elif a.phase=='snapshots':snapshots_by_version()
    else:export()
if __name__=='__main__':main()
