"""Small ABI/HF canaries for later revisions; NEVER full snapshots."""
from decimal import Decimal as D
from .h1 import plan,State
from .common import DATA,SOURCE,read,save,write,now
from defi_data.rpc import Rpc

def run():
    seed=read(SOURCE/'processed/borrower_universe.csv');results=[]
    for item in plan():
        if item['quarter']<'2025Q1':continue
        eligible=sorted((r for r in seed if int(r['first_borrow_block'])<=item['block']),key=lambda r:(int(r['first_borrow_block']),r['account']))
        wallets=sorted({r['account'] for r in eligible[:32]+eligible[-32:]})
        result=dict(quarter=item['quarter'],block=item['block'],full_snapshot_complete=False,
          scope='64 early/recent borrower ABI/HF canaries only; NOT census coverage',updated_utc=now())
        try:
            rpc=Rpc(DATA/'h1/canary_rpc',batch_size=400,multicall=True,cache_individual=False,timeout=15,retry_attempts=1)
            state=State(rpc,item['block']);rows=state.batch(wallets)
            result.update(status='passed',pool_revision=state.revision,wallets_checked=len(rows),active_wallets=sum(D(r[1])>0 for r in rows))
        except Exception as exc:
            result.update(status='error',error_kind=getattr(exc,'kind',type(exc).__name__),error=str(exc)[:300])
            if hasattr(exc,'reconciliation'):
                write(DATA/'h1/canary'/item['quarter']/'failed_reconciliation.csv',exc.reconciliation)
                write(DATA/'h1/canary'/item['quarter']/'failed_positions.csv',exc.positions)
        results.append(result);save(DATA/'h1/canary_report.json',results)
        print(result,flush=True)
    return results

if __name__=='__main__':run()
