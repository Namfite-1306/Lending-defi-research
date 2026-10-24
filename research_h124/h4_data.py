"""Block-timestamp-aligned oracle controls, sampled gas and upgrade history.

No minute-price interpolation, peg substitution, or quarterly HF interpolation.
Raw blocks checkpoint separately; never update the frozen historical dataset.
"""
import argparse,json,sqlite3,time,math
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
from pathlib import Path
import numpy as np
from defi_data.rpc import Rpc
from defi_data.evm import keccak,addr
from defi_data.pipeline import call
from .v2_common import *

POOL='0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2'

def block_connection():
    DATA.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(DATA/'headers.sqlite',timeout=30)
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('CREATE TABLE IF NOT EXISTS headers(block INTEGER PRIMARY KEY,stamp INTEGER,hash TEXT,parent TEXT,base_fee TEXT,gas_used INTEGER,gas_limit INTEGER)')
    return c

def header_row(h,expected=None):
    b=int(h['number'],16)
    if expected is not None and b!=expected:raise ValueError('Wrong returned header number')
    if not h.get('hash') or not h.get('parentHash'):raise ValueError('Missing header identity')
    fee=int(h['baseFeePerGas'],16);used=int(h['gasUsed'],16);limit=int(h['gasLimit'],16)
    if fee<0 or not 0<=used<=limit or limit<=0:raise ValueError('Invalid header gas data')
    return b,int(h['timestamp'],16),h['hash'],h['parentHash'],str(fee),used,limit

def oracle_rows():return read(SOURCE/'processed/chainlink_price_updates.csv')

def collect(minutes=120,batch=80):
    with worker_lock(DATA/'headers.lock'):
        rows=oracle_rows();blocks=sorted({int(r['block']) for r in rows});c=block_connection()
        done={r[0] for r in c.execute('SELECT block FROM headers')};pending=[b for b in blocks if b not in done]
        save(DATA/'header_progress.json',{'updated_utc':now(),'required_headers':len(blocks),'collected_headers':len(done.intersection(blocks)),
          'complete':not pending,'errors':[],'source':'eth_getBlockByNumber at fixed oracle update blocks','max_inflight_requests':2})
        deadline=time.monotonic()+minutes*60;errors=[]
        def fetch(chunk):
            rpc=Rpc(DATA/'rpc_headers',batch_size=batch,cache_individual=False,use_cache=False,timeout=12,retry_attempts=1)
            values=rpc.many([('eth_getBlockByNumber',[hex(b),False]) for b in chunk])
            material=[header_row(h,b) for b,h in zip(chunk,values)]
            if len(material)!=len(chunk):raise ValueError('Missing headers')
            return material
        # Only two in-flight public requests; SQLite commits and progress remain
        # serial. No unbounded queue, and deadline stops new submissions.
        chunks=iter(pending[i:i+batch] for i in range(0,len(pending),batch));count=0;halt=False;network_failures=0
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures={}
            def submit():
                chunk=next(chunks,None)
                if chunk is not None:futures[executor.submit(fetch,chunk)]=chunk
            submit();submit()
            while futures:
                finished,_=wait(futures,return_when=FIRST_COMPLETED)
                for future in finished:
                    chunk=futures.pop(future)
                    try:
                        material=future.result()
                        with c:c.executemany('INSERT OR REPLACE INTO headers VALUES (?,?,?,?,?,?,?)',material)
                        done.update(chunk)
                        network_failures=0
                    except Exception as exc:
                        errors.append({'first_block':chunk[0],'last_block':chunk[-1],'kind':getattr(exc,'kind',type(exc).__name__)})
                        halt=halt or getattr(exc,'kind','') in ('authorization','rate_limit')
                        network_failures+=int(getattr(exc,'kind','')=='network')
                        halt=halt or network_failures>=3
                    status={'updated_utc':now(),'required_headers':len(blocks),'collected_headers':len(done.intersection(blocks)),
                      'complete':all(b in done for b in blocks),'errors':errors[-20:],'source':'eth_getBlockByNumber at fixed oracle update blocks','max_inflight_requests':2}
                    save(DATA/'header_progress.json',status);count+=1
                    if count%10==0:print('H4 HEADERS',status['collected_headers'],'/',len(blocks),flush=True)
                    if not halt and time.monotonic()<deadline:submit()
        c.close();return load(DATA/'header_progress.json',{})

def upgrades():
    bounds=load(SOURCE/'block_range.json');path=DATA/'pool_upgrades.json'
    if load(path,{}).get('complete'):return load(path)
    rpc=Rpc(DATA/'rpc_upgrades',batch_size=50,multicall=True,timeout=12,retry_attempts=1)
    topic='0x'+keccak(b'Upgraded(address)').hex()
    logs=rpc.logs(POOL,[topic],bounds['start_block'],bounds['end_block'])
    events=[]
    revision=int(call(rpc,POOL,'POOL_REVISION()',[],bounds['start_block'])[0],16)
    events.append({'block':bounds['start_block'],'stamp':int(rpc.block(bounds['start_block'])['timestamp'],16),'revision':revision,'initial':True})
    for row in sorted(logs,key=lambda r:(int(r['blockNumber'],16),int(r['logIndex'],16))):
        b=int(row['blockNumber'],16);h=rpc.block(b)
        events.append({'block':b,'stamp':int(h['timestamp'],16),'hash':h['hash'],'revision':int(call(rpc,POOL,'POOL_REVISION()',[],b)[0],16),
          'implementation':addr(row['topics'][1][2:]),'tx':row['transactionHash'],'log_index':int(row['logIndex'],16)})
    result={'complete':True,'start_block':bounds['start_block'],'end_block':bounds['end_block'],'events':events,
      'scope':'Pool Upgraded logs; end-of-block revision, available strictly after activation timestamp. Not every reserve governance change.'}
    save(path,result);return result

def asof(t,available,values):
    """Strictly before bin start, including block-order availability."""
    available=np.asarray(available,dtype=np.int64);values=np.asarray(values)
    if not len(available):return np.full(len(t),np.nan),np.full(len(t),-1,dtype=int)
    if np.any(np.diff(available)<0):raise ValueError('Unsorted availability')
    idx=np.searchsorted(available,t,side='left')-1
    output=np.full(len(t),np.nan);good=idx>=0;output[good]=values[idx[good]]
    return output,idx

def build(bin_minutes=5):
    with worker_lock(DATA/'panel.lock'):
        return materialize(bin_minutes)

def verified_prefix(raw,headers):
    """Stop before the first unverified update, never bridge an RPC gap."""
    required=sorted({int(r['block']) for r in raw})
    first_missing=next((b for b in required if b not in headers),None)
    if first_missing is None:raise ValueError('All headers available: use full build')
    verified=[b for b in required if b<first_missing]
    if not verified:raise ValueError('No verified initial prefix')
    end=(headers[verified[-1]][1]//300)*300
    return [r for r in raw if int(r['block'])<first_missing],{b:headers[b] for b in verified},end,first_missing

def materialize(bin_minutes=5,prefix=False):
    from .h4 import panel
    t,y,old,old_valid,old_scope=panel(bin_minutes=bin_minutes)
    c=block_connection();headers={r[0]:r for r in c.execute('SELECT * FROM headers')};c.close()
    raw=oracle_rows();required={int(r['block']) for r in raw}
    missing=required-set(headers)
    if missing and not prefix:
        save(OUT/'h4_data_readiness.json',{'status':'waiting_for_headers','missing_headers':len(missing),'required_headers':len(required),'updated_utc':now()})
        raise ValueError(f'{len(missing)} oracle availability headers missing; do not forward-fill across unverified updates')
    scope_type='full_target';first_missing=None
    if prefix:
        raw,headers,end,first_missing=verified_prefix(raw,headers)
        mask=t+bin_minutes*60<=end;t=t[mask];y=y[mask];old=old[mask];old_valid=old_valid[mask]
        if not len(t):raise ValueError('Empty verified prefix')
        old_scope={**old_scope,'target_end_exclusive':old_scope['end_exclusive'],'end_exclusive':__import__('defi_models.core',fromlist=['iso']).iso(int(t[-1]+bin_minutes*60)),
          'events':int(y.sum()),'bins':len(t),'excluded_covariate_bins':int((~old_valid).sum())}
        scope_type='verified_prefix_not_full_target'
    tag='h4_prefix' if prefix else 'h4';panel_path=DATA/(tag+'_panel_5min.npz')
    names=[];columns=[];coverage=[];series={}
    for feed in ['ETH/USD','BTC/USD','USDC/USD','USDT/USD','DAI/USD']:
        rows=sorted((r for r in raw if r['feed']==feed),key=lambda r:(int(r['block']),int(r['round_id'])))
        available=np.array([headers[int(r['block'])][1] for r in rows]);updated=np.array([int(r['stamp']) for r in rows]);price=np.array([float(r['price_usd']) for r in rows])
        if np.any(price<=0) or np.any(updated>available):raise ValueError('Invalid quote time/value')
        p,index=asof(t,available,price);update,_=asof(t,available,updated);age=t-update
        max_age=7200 if feed in ['ETH/USD','BTC/USD'] else 129600
        valid=(index>=0)&(age>=0)&(age<=max_age);p[~valid]=np.nan
        series[feed]=(p,available,price,valid)
        symbol=feed.split('/')[0];coverage.append({'feature_group':symbol,'bins':len(t),'valid_bins':int(valid.sum()),'coverage':float(valid.mean()),'max_source_age_seconds':max_age})
        if symbol in ['ETH','BTC']:
            for minutes in [5,60]:
                before,_=asof(t-minutes*60,available,price);before_update,_=asof(t-minutes*60,available,updated)
                ret=np.log(p/before);ret[(t-minutes*60-before_update)>max_age]=np.nan
                names.append(f'{symbol}_oracle_down_{minutes}m');columns.append(np.maximum(-ret,0))
            jumps=np.r_[0,np.abs(np.diff(np.log(price)))];jump,_=asof(t,available,jumps)
            names.extend([f'{symbol}_oracle_last_jump',f'{symbol}_oracle_log_age']);columns.extend([np.where(valid,jump,np.nan),np.where(valid,np.log1p(age),np.nan)])
        else:
            names.extend([symbol+'_positive_depeg',symbol+'_negative_depeg']);columns.extend([np.maximum(p-1,0),np.maximum(1-p,0)])
    # A header sampled at the latest known ETH oracle update, not a 5-minute
    # median gas estimate. Its age enters explicitly and max carry is 1 hour.
    eth=sorted({int(r['block']) for r in raw if r['feed']=='ETH/USD'})
    h=[headers[b] for b in eth];a=np.array([r[1] for r in h])
    gas,_=asof(t,a,[int(r[4])/1e9 for r in h]);gas_time,_=asof(t,a,a);gas_age=t-gas_time
    gas[gas_age>3600]=np.nan
    names.extend(['sampled_base_fee_log_gwei','sampled_header_log_age']);columns.extend([np.log1p(gas),np.where(gas_age<=3600,np.log1p(gas_age),np.nan)])
    coverage.append({'feature_group':'sampled_gas','bins':len(t),'valid_bins':int(np.isfinite(gas).sum()),'coverage':float(np.isfinite(gas).mean()),'max_source_age_seconds':3600})
    upgrade=load(DATA/'pool_upgrades.json',{})
    if not upgrade.get('complete'):raise ValueError('Pool upgrade history incomplete')
    events=upgrade['events'];revision,_=asof(t,[r['stamp'] for r in events],[r['revision'] for r in events])
    for rev in sorted({r['revision'] for r in events}-{events[0]['revision']}):
        names.append('pool_revision_'+str(rev));columns.append((revision==rev).astype(float))
    # Existing volatility and time controls remain a separately named baseline.
    names+=['ETH_rv24h','BTC_rv24h','hour_sin','hour_cos'];columns+=[old[:,j] for j in [4,5,6,7]]
    X=np.column_stack(columns);OUT.mkdir(parents=True,exist_ok=True)
    write_npz(panel_path,t=t,y=y,X=X,old=old,old_valid=old_valid,names=np.array(names))
    import hashlib
    ledger=hashlib.sha256()
    for b in sorted(headers):ledger.update(json.dumps(headers[b],separators=(',',':')).encode()+b'\n')
    write(OUT/(tag+'_feature_coverage.csv'),coverage)
    definitions=[{'feature':n,'timing':'strictly before bin start','status':'available'} for n in names]
    definitions += [{'feature':n,'timing':'quarter end observations only; not interpolated to 5m','status':'quarterly_auxiliary_not_primary_fit'} for n in ['collateral_basket','LST_basis','WBTC_basis','HF_near_threshold','utilization']]
    definitions += [{'feature':'DEX_depth','timing':'pre-event/+15m/+60m samples only','status':'sparse_event_quotes_not_full_period'}]
    write(OUT/(tag+'_feature_dictionary.csv'),definitions)
    result={'status':'completed_scoped','updated_utc':now(),'bins':len(t),'events':int(y.sum()),'features':names,'source':old_scope,
      'scope_type':scope_type,'target_period_complete':not prefix,'first_unverified_block':first_missing,
      'panel_sha256':digest(panel_path),'headers':len(headers),'header_ledger_sha256':ledger.hexdigest(),
      'oracle_updates_sha256':digest(SOURCE/'processed/chainlink_price_updates.csv'),'code_sha256':digest(__file__),'upgrade_history_sha256':digest(DATA/'pool_upgrades.json'),
      'limitations':['Oracle-implied returns, not continuous market prices','Gas sampled at latest ETH oracle header, not previous-bin median; sampling tied to oracle activity',
        'Stablecoin freshness threshold 36h is an explicit sensitivity assumption','No quarterly HF interpolation, no basis/DEX/utilization imputation','New feature selection is exploratory after prior test evaluation']}
    save(OUT/(tag+'_data_readiness.json'),result);return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--minutes',type=float,default=120);p.add_argument('--batch',type=int,default=80);p.add_argument('--build-only',action='store_true');p.add_argument('--verified-prefix',action='store_true');a=p.parse_args()
    if a.verified_prefix:
        with worker_lock(DATA/'panel.lock'):print(json.dumps(materialize(prefix=True),ensure_ascii=False),flush=True)
        return
    if not a.build_only:collect(a.minutes,a.batch);upgrades()
    print(json.dumps(build(),ensure_ascii=False),flush=True)
if __name__=='__main__':main()
