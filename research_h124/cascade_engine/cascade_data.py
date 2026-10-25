"""Full pre-event census and time-aligned quote paths, separate from quarters."""
import argparse,time,json
from datetime import datetime,timezone
from defi_data.rpc import Rpc
from defi_live.liquidity import POOLS,pool_quotes
from .v2_common import *

def plan():
    path=DATA/'cascade_snapshots/quarter_plan.json'
    if path.exists():return load(path)
    rpc=Rpc(DATA/'cascade_rpc',batch_size=80,multicall=True,timeout=12,retry_attempts=1)
    events=read(CANONICAL/'results/stress_validation_20261024/backtest_event_plan.csv');seed=read(SOURCE/'processed/borrower_universe.csv');rows=[]
    for e in sorted(events,key=lambda r:r['date']):
        b=int(e['first_event_block'])-1;h=rpc.block(b)
        rows.append({'quarter':e['date'],'event_date':e['date'],'block':b,'hash':h['hash'],'stamp':int(h['timestamp'],16),
          'cutoff_exclusive_utc':datetime.fromtimestamp(int(h['timestamp'],16)+1,timezone.utc).isoformat(),
          'historical_borrowers':sum(int(r['first_borrow_block'])<=b for r in seed),'status':'pending',
          'selection':'retrospective high-liquidation dates; pre-event borrower census, not liquidation-conditioned borrower selection'})
    save(path,rows);return rows

def quotes():
    rpc=Rpc(DATA/'cascade_rpc',batch_size=80,multicall=True,timeout=12,retry_attempts=1);rows=[];errors=[]
    bounds=load(SOURCE/'block_range.json');items=plan()
    for e in items:
        for minutes in [0,15,60]:
            folder=DATA/'cascade_quotes'/e['quarter']/str(minutes);file=folder/'quotes.csv'
            if file.exists():rows+=read(file);continue
            at=e['stamp']+minutes*60
            b=e['block'] if minutes==0 else rpc.block_at(at,bounds['end_block'])-1
            local=[]
            for pool in POOLS:
                try:
                    values,failed=pool_quotes(rpc,pool,b,sizes=(1000,5000,10000,50000,100000,500000,1000000))
                    local += [dict(event_date=e['quarter'],offset_minutes=minutes,block_hash=rpc.block(b)['hash'],**r) for r in values]
                    errors += [dict(event_date=e['quarter'],offset_minutes=minutes,**r) for r in failed]
                except Exception as exc:errors.append({'event_date':e['quarter'],'offset_minutes':minutes,'pool':pool,'kind':getattr(exc,'kind',type(exc).__name__)})
            if local:write(file,local);rows+=local
            write(OUT/'cascade/quote_path.csv',rows);save(OUT/'cascade/quote_collection.json',{'updated_utc':now(),'quotes':len(rows),'errors':errors,'complete':False})
            print('CASCADE QUOTES',e['quarter'],minutes,len(local),flush=True)
    save(OUT/'cascade/quote_collection.json',{'updated_utc':now(),'quotes':len(rows),'errors':errors,'complete':not errors,
      'scope':'two pools at pre-event, +15m, +60m; sparse measured path, not continuous liquidity or routed execution'})
    return rows

def run(minutes=360):
    from .h1 import run as collect
    items=plan();quotes()
    collect(source=SOURCE,out=DATA/'cascade_snapshots',minutes=minutes,batch=400)
    print('CASCADE SNAPSHOTS COLLECTION PASS FINISHED',flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--minutes',type=float,default=360);a=p.parse_args();run(a.minutes)
