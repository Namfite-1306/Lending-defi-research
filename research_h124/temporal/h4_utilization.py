"""Hourly-as-of reserve usage/rate panel, exact historical available liquidity.

Eth_call batches wrap each block's calls in Multicall separately, preserving
block identity. Older pools use underlying cash; virtual-accounting pools use
their recorded virtual balance. No debt/supply shortcut or GHO utilization proxy.
"""
import argparse,json,sqlite3,time
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
import numpy as np
from defi_data.rpc import Rpc
from defi_data.pipeline import PROVIDER,call_request
from defi_data.evm import words,uint,addr
from defi_data.multicall import encode_aggregate,decode_aggregate
from .h4_data import block_connection,oracle_rows,asof,POOL
from .v2_common import *

TOKENS={'WETH':'0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2','USDC':'0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'}
MULTICALL='0xca11bde05977b3631167028862be2a173976ca11'

def aggregates(rpc,specs):
    queries=[]
    for block,calls in specs:
        queries.append(('eth_call',[{'to':MULTICALL,'data':encode_aggregate([call_request(target,sig,args,block)[1][0] for target,sig,args in calls]),'gas':hex(25000000)},hex(block)]))
    values=rpc.many(queries);output=[]
    for value,(_,calls) in zip(values,specs):
        decoded=decode_aggregate(value)
        if len(decoded)!=len(calls) or not all(ok for ok,_ in decoded):raise ValueError('Incomplete historical reserve responses')
        output.append([words(raw) for ok,raw in decoded])
    return output

def fetch_chunk(blocks):
    rpc=Rpc(DATA/'utilization_rpc',batch_size=20,use_cache=False,cache_individual=False,timeout=12,retry_attempts=1)
    meta=aggregates(rpc,[(b,[(PROVIDER,'getPoolDataProvider()',[]),(POOL,'POOL_REVISION()',[])]+[(POOL,'getConfiguration(address)',[t]) for t in TOKENS.values()]) for b in blocks])
    specs=[];virtual={}
    for b,w in zip(blocks,meta):
        provider=addr(w[0][0]);revision=uint(w[1][0]);calls=[]
        if not 1<=revision<=11:raise ValueError('Unreviewed Pool revision for reserve usage')
        for i,token in enumerate(TOKENS.values()):
            v=revision>=8 or bool((uint(w[2+i][0])>>252)&1);virtual[b,token]=v
            calls += [(provider,'getReserveData(address)',[token])]
            calls += [(POOL,'getVirtualUnderlyingBalance(address)',[token])] if v else [(provider,'getReserveTokensAddresses(address)',[token])]
        specs.append((b,calls))
    state=aggregates(rpc,specs);cash_specs=[];cash_keys=[]
    for b,w in zip(blocks,state):
        calls=[];keys=[]
        for i,token in enumerate(TOKENS.values()):
            if not virtual[b,token]:calls.append((token,'balanceOf(address)',[addr(w[2*i+1][0])]));keys.append(token)
        if calls:cash_specs.append((b,calls));cash_keys.append(keys)
    cash={}
    for (b,_),keys,w in zip(cash_specs,cash_keys,aggregates(rpc,cash_specs) if cash_specs else []):
        for token,value in zip(keys,w):cash[b,token]=uint(value[0])
    rows=[]
    for b,w in zip(blocks,state):
        for i,(symbol,token) in enumerate(TOKENS.items()):
            reserve=w[2*i]
            if len(reserve)!=12:raise ValueError('Unknown reserve data ABI')
            available=uint(w[2*i+1][0]) if virtual[b,token] else cash[b,token]
            debt=uint(reserve[3])+uint(reserve[4]);total=available+debt
            if total<=0:raise ValueError('Empty utilization denominator')
            rows.append((b,symbol,str(available),str(debt),debt/total,uint(reserve[6])/1e27,int(virtual[b,token])))
    return rows

def collect(minutes=180):
    with worker_lock(DATA/'utilization.lock'):
        if not load(DATA/'header_progress.json',{}).get('complete'):raise ValueError('Wait for verified oracle headers')
        c=block_connection();headers={b:t for b,t in c.execute('SELECT block,stamp FROM headers')};c.close();raw=oracle_rows()
        eth=sorted({int(r['block']) for r in raw if r['feed']=='ETH/USD'});times=[headers[b] for b in eth]
        with np.load(DATA/'h4_panel_5min.npz') as p:t=p['t'][::12]
        t=t[t>=t[0]+60*3600]  # same warmup as H4; no pre-deployment seed calls
        chosen,index=asof(t,times,eth);valid=(index>=0)&((t-np.array(times)[np.maximum(index,0)])<=7200)
        blocks=sorted({int(b) for b in chosen[valid]});db=sqlite3.connect(DATA/'reserve_usage.sqlite',timeout=30);db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE IF NOT EXISTS reserves(block INTEGER,symbol TEXT,available TEXT,debt TEXT,usage REAL,borrow_apr REAL,virtual INTEGER,PRIMARY KEY(block,symbol))')
        done={b for b,n in db.execute('SELECT block,count(*) FROM reserves GROUP BY block') if n==2};pending=[b for b in blocks if b not in done]
        save(DATA/'utilization_progress.json',{'updated_utc':now(),'required_blocks':len(blocks),'complete_blocks':len(done),'complete':not pending,'errors':[]})
        deadline=time.monotonic()+minutes*60;chunks=iter(pending[i:i+20] for i in range(0,len(pending),20));errors=[];count=0;halt=False;network_failures=0
        with ThreadPoolExecutor(max_workers=2) as ex:
            futures={}
            def submit():
                chunk=next(chunks,None)
                if chunk is not None:futures[ex.submit(fetch_chunk,chunk)]=chunk
            submit();submit()
            while futures:
                finished,_=wait(futures,return_when=FIRST_COMPLETED)
                for f in finished:
                    chunk=futures.pop(f)
                    try:
                        rows=f.result()
                        if len(rows)!=2*len(chunk):raise ValueError('Incomplete reserve batch')
                        with db:db.executemany('INSERT OR REPLACE INTO reserves VALUES (?,?,?,?,?,?,?)',rows)
                        done.update(chunk)
                        network_failures=0
                    except Exception as exc:
                        errors.append({'first_block':chunk[0],'kind':getattr(exc,'kind',type(exc).__name__)});halt=halt or getattr(exc,'kind','') in ['rate_limit','authorization']
                        network_failures+=int(getattr(exc,'kind','')=='network');halt=halt or network_failures>=3
                    save(DATA/'utilization_progress.json',{'updated_utc':now(),'required_blocks':len(blocks),'complete_blocks':len(done),'complete':set(blocks)<=done,'errors':errors[-10:]})
                    count+=1
                    if count%10==0:print('H4 RESERVE USAGE',len(done),'/',len(blocks),flush=True)
                    if not halt and time.monotonic()<deadline:submit()
        rows=list(db.execute('SELECT * FROM reserves ORDER BY block,symbol'));db.close()
        if not set(blocks)<=done:raise ValueError('Reserve context incomplete, checkpoint retained')
        write(OUT/'h4_hourly_reserve_usage.csv',[dict(zip(['block','symbol','available_native_raw','debt_native_raw','borrow_usage_ratio','variable_borrow_APR','virtual_accounting'],r)) for r in rows])
        return rows,headers

def build():
    c=block_connection();headers={b:t for b,t in c.execute('SELECT block,stamp FROM headers')};c.close()
    db=sqlite3.connect(DATA/'reserve_usage.sqlite');rows=list(db.execute('SELECT * FROM reserves ORDER BY block,symbol'));db.close()
    base_hash=digest(DATA/'h4_panel_5min.npz')
    with np.load(DATA/'h4_panel_5min.npz') as p:arrays={k:p[k] for k in p.files}
    t=arrays['t'];columns=[];names=[];coverage=[]
    for symbol in TOKENS:
        rs=[r for r in rows if r[1]==symbol];at=[headers[r[0]] for r in rs]
        available,idx=asof(t,at,at);age=t-available;good=(idx>=0)&(age<=7200)
        for key,values in [('borrow_usage',[r[4] for r in rs]),('borrow_APR',[r[5] for r in rs])]:
            value,_=asof(t,at,values);value[~good]=np.nan;columns.append(value);names.append('reserve_'+symbol+'_'+key)
        columns.append(np.where(good,np.log1p(age),np.nan));names.append('reserve_'+symbol+'_log_age')
        coverage.append({'symbol':symbol,'bins':len(t),'valid_bins':int(good.sum()),'coverage':float(good.mean()),'max_age_seconds':7200})
    arrays['X']=np.column_stack([arrays['X'],*columns]);arrays['names']=np.r_[arrays['names'],np.array(names)]
    if digest(DATA/'h4_panel_5min.npz')!=base_hash:raise ValueError('Core panel changed during reserve build; retry')
    write_npz(DATA/'h4_util_panel_5min.npz',**arrays);write(OUT/'h4_reserve_usage_coverage.csv',coverage)
    result={'status':'completed_scoped','updated_utc':now(),'panel_sha256':digest(DATA/'h4_util_panel_5min.npz'),'base_panel_sha256':base_hash,
      'reserve_source_sha256':digest(OUT/'h4_hourly_reserve_usage.csv'),'features':names,'limitations':['Hourly-as-of anchors from verified oracle-update blocks, maximum source age two hours','Correct virtual/actual liquidity at each historical block; WETH/USDC only','Utilization is predictive context and may itself reflect previous liquidations, not an exogenous instrument']}
    save(OUT/'h4_util_data_readiness.json',result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--minutes',type=float,default=180);p.add_argument('--wait-minutes',type=float,default=180);a=p.parse_args()
    deadline=time.monotonic()+a.wait_minutes*60
    def core_ready():
        from . import h4_data
        r=load(OUT/'h4_data_readiness.json',{})
        return r.get('status')=='completed_scoped' and r.get('code_sha256')==digest(h4_data.__file__) and r.get('panel_sha256')==digest(DATA/'h4_panel_5min.npz')
    while not core_ready():
        if time.monotonic()>=deadline:raise ValueError('Core H4 panel not ready before wait budget')
        time.sleep(15)
    collect(a.minutes);print(build(),flush=True)
