"""Collect pre-event, block-aligned quotes without changing the frozen dataset."""
import argparse,csv,json,time
from pathlib import Path
from defi_live.liquidity import pool_quotes,POOLS
from defi_data.rpc import Rpc
from defi_models.core import write_csv

def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--events',type=int,default=1);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    rpc=Rpc(a.out/'rpc_cache',batch_size=20,multicall=True,timeout=10,retry_attempts=1)
    with a.plan.open(encoding='utf-8-sig',newline='') as f:events=list(csv.DictReader(f))[:a.events]
    quotes=[];errors=[]
    for event in events:
        block=int(event['first_event_block'])-1
        for pool in POOLS:
            try:
                rows,failed=pool_quotes(rpc,pool,block,sizes=(1000,2000,5000,10000,20000,50000,100000,200000,500000,1000000))
                quotes.extend(dict(event_date=event['date'],**r) for r in rows);errors+=failed
            except Exception as exc:errors.append({'date':event['date'],'pool':pool,'kind':getattr(exc,'kind',type(exc).__name__)})
            write_csv(a.out/'pre_event_quotes.csv',quotes)
    (a.out/'quote_collection.json').write_text(json.dumps({'quotes':len(quotes),'errors':errors,'updated_at':time.time(),'scope':'two Uniswap V3 pools at pre-event block only; not full event price path'},indent=2),encoding='utf8')
    print('Pre-event quotes:',len(quotes),'errors:',len(errors))

if __name__=='__main__':main()
