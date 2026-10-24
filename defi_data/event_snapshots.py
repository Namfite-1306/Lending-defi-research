"""Resumable historical pre-event snapshots in a separate, unfrozen output.

Each account batch commits positions and validation atomically in SQLite. No
liquidation-conditioned borrower selection: seed uses prior Borrow blocks only.
Incomplete output must not be supplied to research models as a full snapshot.
"""
import argparse,csv,json,sqlite3,time,tempfile
from pathlib import Path
from decimal import Decimal
from .rpc import Rpc
from .pipeline import CONTRACTS,call_request
from .evm import words,uint
from .expansion import aave_positions


def borrowers_before(universe,block):
    return sorted({r['account'] for r in universe if int(r['first_borrow_block'])<=block})


def export_completed(db,folder,status):
    from defi_models.core import write_csv,write_json
    if not status['full_snapshot_complete'] or status['passed']!=status['active_debt_wallets']:raise ValueError('Incomplete/unreconciled historical snapshot cannot be exported as full')
    positions=[];checks=[]
    for debt,raw_checks,raw_positions in db.execute('SELECT debt,checks,positions FROM accounts ORDER BY account'):
        if Decimal(debt)<=0:continue
        check=json.loads(raw_checks);checks.append(dict(check,block=status['block'],scope='all prior Borrow cohort at fixed block'))
        for r in json.loads(raw_positions):
            positions.append(dict(r,block=status['block'],token=r['token_address'],effective_lt=r['effective_liquidation_threshold'],selection='all prior Borrow cohort at fixed block'))
    folder=Path(folder);write_csv(folder/'positions.csv',positions);write_csv(folder/'validation.csv',checks)
    write_json(folder/'scope.json',dict(status,failed_debt_usd='0',requires_independent_audit_and_freeze=True))


def collect(seed,plan,out,minutes=30,batch=20,event_limit=1):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);deadline=time.monotonic()+minutes*60
    with Path(seed).open(encoding='utf-8-sig',newline='') as f:universe=list(csv.DictReader(f))
    with Path(plan).open(encoding='utf-8-sig',newline='') as f:events=list(csv.DictReader(f))[:event_limit]
    rpc=Rpc(out/'rpc_cache',batch_size=50,multicall=True,use_cache=True,timeout=12,retry_attempts=1)
    summary=[]
    for event in events:
        block=int(event['first_event_block'])-1;folder=out/event['date'];folder.mkdir(exist_ok=True)
        db=sqlite3.connect(folder/'snapshot.sqlite',timeout=30)
        db.execute('CREATE TABLE IF NOT EXISTS accounts(account TEXT PRIMARY KEY, debt TEXT, checks TEXT, positions TEXT)')
        wallets=borrowers_before(universe,block)
        identity=rpc.one('eth_getBlockByNumber',[hex(block),False]);status={'date':event['date'],'block':block,'hash':identity['hash'],
          'source_stamp':int(identity['timestamp'],16),'historical_borrowers':len(wallets),'timing':'block end before first liquidation of selected UTC day',
          'selection':'all seed Borrow accounts with first_borrow_block <= cutoff; not future liquidated-wallet selection',
          'full_snapshot_complete':False,'status':'collecting','borrower_history_complete':all(r['history_complete']=='True' for r in universe)}
        metadata=folder/'identity.json'
        if metadata.exists() and json.loads(metadata.read_text())['hash']!=identity['hash']:raise ValueError('Historical snapshot block hash changed')
        metadata.write_text(json.dumps(status,indent=2),encoding='utf8')
        def save_status():
            rows=db.execute('SELECT debt,checks FROM accounts').fetchall()
            status.update(wallets_scanned=len(rows),active_debt_wallets=sum(Decimal(r[0])>0 for r in rows),
              passed=sum(bool(json.loads(r[1]).get('passed')) for r in rows if Decimal(r[0])>0),
              reported_debt_usd=str(sum((Decimal(r[0]) for r in rows),Decimal(0))),
              updated_at=time.time(),full_snapshot_complete=len(rows)==len(wallets),
              status='completed' if len(rows)==len(wallets) else status['status'])
            temp=folder/'progress.tmp';temp.write_text(json.dumps(status,indent=2),encoding='utf8');temp.replace(folder/'progress.json')
        try:
            done={r[0] for r in db.execute('SELECT account FROM accounts')};pending=[a for a in wallets if a not in done]
            for start in range(0,len(pending),batch):
                if time.monotonic()>=deadline:status['status']='time_budget_reached';break
                group=pending[start:start+batch]
                account_data=rpc.many([call_request(CONTRACTS['aave_v3'][0],'getUserAccountData(address)',[a],block) for a in group])
                active=[a for a,raw in zip(group,account_data) if uint(words(raw)[1])>0]
                modes=rpc.many([call_request(CONTRACTS['aave_v3'][0],'getUserEMode(address)',[a],block) for a in active]) if active else []
                by_account={};checks={}
                if active:
                    with tempfile.TemporaryDirectory(dir=folder) as tmp:
                        snapshot=aave_positions(rpc,block,[(a,uint(words(raw)[0])) for a,raw in zip(active,modes)],Path(tmp))
                        status.update({k:v for k,v in snapshot['scope'].items() if k in ['pool','oracle','provider']})
                        if snapshot['checks']:status['pool_revision']=snapshot['checks'][0]['pool_revision']
                        checks={r['account']:r for r in snapshot['checks']}
                        if set(checks)!=set(active) or not all(r['passed'] for r in checks.values()):raise ValueError('Historical HF reconciliation failed; batch not committed')
                        for r in snapshot['positions']:by_account.setdefault(r['account'],[]).append(r)
                        # Retain per-reserve configuration and provenance from this block.
                        (folder/'reserve_configuration.json').write_text(json.dumps(snapshot['reserves'],default=str,indent=2),encoding='utf8')
                with db:
                    for a,raw in zip(group,account_data):
                        debt=Decimal(uint(words(raw)[1]))/10**8
                        db.execute('INSERT INTO accounts VALUES (?,?,?,?)',(a,str(debt),json.dumps(checks.get(a,{}),default=str),json.dumps(by_account.get(a,[]),default=str)))
                save_status();print(json.dumps({k:status[k] for k in ['date','wallets_scanned','historical_borrowers','active_debt_wallets','passed']}),flush=True)
            save_status()
            if status['full_snapshot_complete']:export_completed(db,folder,status)
        except Exception as exc:
            status.update(status='error',error_kind=getattr(exc,'kind',type(exc).__name__),error=str(exc)[:350]);save_status()
        finally:db.close()
        summary.append(status)
        if time.monotonic()>=deadline:break
    (out/'collection_status.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    return summary


def main():
    p=argparse.ArgumentParser();p.add_argument('--seed',type=Path,required=True);p.add_argument('--plan',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--minutes',type=float,default=30);p.add_argument('--batch',type=int,default=20);p.add_argument('--events',type=int,default=1);a=p.parse_args()
    if not 0<a.minutes<=1440 or not 1<=a.batch<=200 or not 1<=a.events<=5:p.error('Invalid runtime/batch/event limits')
    print(json.dumps(collect(a.seed,a.plan,a.out,a.minutes,a.batch,a.events),indent=2))

if __name__=='__main__':main()
