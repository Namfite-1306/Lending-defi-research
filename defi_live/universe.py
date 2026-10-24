"""Persistent rolling account-data census, separate from coherent stress snapshots.

Account rows from different blocks must never be pooled into a single Portfolio.
The historical seed and live tail can have an uncollected discovery gap.
"""
import csv
import hashlib
import json
import re
import time
from decimal import Decimal
from pathlib import Path
from defi_data.pipeline import CONTRACTS, call_request
from defi_data.evm import words, uint


class UniverseScanner:
    def __init__(self, store, rpc, seed=None, batch_size=200, freshness_seconds=3600):
        if not 1 <= batch_size <= 1000:raise ValueError('Universe batch must be 1..1000')
        self.store=store;self.rpc=rpc;self.batch_size=batch_size;self.freshness=freshness_seconds
        with store.db() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS borrower_census (
              account TEXT PRIMARY KEY, source TEXT, block INTEGER, hash TEXT, stamp INTEGER,
              checked_at REAL, debt_usd REAL, hf REAL);
              CREATE INDEX IF NOT EXISTS census_age ON borrower_census(stamp,account);''')
        if seed:
            path=Path(seed)
            with path.open(encoding='utf-8-sig',newline='') as f:
                seed_rows=list(csv.DictReader(f));accounts=sorted({r['account'].lower() for r in seed_rows})
            digest=hashlib.sha256(path.read_bytes()).hexdigest();prior=store.meta('universe_seed',{})
            if prior.get('sha256') and prior['sha256']!=digest:raise ValueError('Universe seed changed; use a new state directory')
            if not all(re.fullmatch('0x[0-9a-f]{40}',a) for a in accounts):raise ValueError('Invalid universe seed')
            with store.db() as c:
                c.executemany('INSERT OR IGNORE INTO borrower_census(account,source) VALUES (?,?)',[(a,'historical_seed') for a in accounts])
            bounds=path.parent.parent/'block_range.json'
            end=json.loads(bounds.read_text(encoding='utf8'))['end_block'] if bounds.exists() else None
            store.set_meta('universe_seed',{'file':path.name,'accounts':len(accounts),'end_block':end,'sha256':digest,
              'history_complete':bool(seed_rows) and all(r.get('history_complete')=='True' for r in seed_rows),
              'scope':'historical seed + discovery backfill + live Borrow events; check gap status'})

    def discover(self):
        with self.store.db() as c:
            c.execute("INSERT OR IGNORE INTO borrower_census(account,source) SELECT DISTINCT account,'live_Borrow' FROM events WHERE protocol='aave_v3' AND name='Borrow' AND account<>''")
            # Remove orphan observations, retaining accounts for rechecking.
            c.execute('''UPDATE borrower_census SET block=NULL,hash=NULL,stamp=NULL,checked_at=NULL,debt_usd=NULL,hf=NULL
              WHERE block IS NOT NULL AND NOT EXISTS (SELECT 1 FROM blocks b WHERE b.number=borrower_census.block AND b.hash=borrower_census.hash)''')

    def scan(self):
        self.discover();block=self.store.meta('cursor')
        if block is None:return
        h=self.store.header(block)
        # Oldest-first guarantees progress across the entire seed; risk priority is
        # used for coherent snapshots, never to starve the census tail.
        with self.store.db() as c:
            accounts=[r[0] for r in c.execute('SELECT account FROM borrower_census ORDER BY coalesce(stamp,0),account LIMIT ?',(self.batch_size,))]
        if not accounts:return
        results=self.rpc.many([call_request(CONTRACTS['aave_v3'][0],'getUserAccountData(address)',[a],block) for a in accounts])
        values=[]
        if len(results)!=len(accounts):raise ValueError('Incomplete universe response')
        for a,result in zip(accounts,results):
            w=words(result)
            if len(w)!=6:raise ValueError('Invalid account-data response')
            debt=float(Decimal(uint(w[1]))/10**8);hf=float(Decimal(uint(w[5]))/10**18) if debt else None
            values.append((block,h['hash'],h['stamp'],time.time(),debt,hf,a))
        fresh=self.rpc.one('eth_getBlockByNumber',[hex(block),False],cache=False)
        if fresh['hash']!=h['hash']:raise ValueError('Universe batch invalidated by reorg')
        with self.store.db() as c:
            canonical=c.execute('SELECT hash FROM blocks WHERE number=?',(block,)).fetchone()
            if not canonical or canonical[0]!=h['hash']:raise ValueError('Universe batch is no longer canonical')
            c.executemany('UPDATE borrower_census SET block=?,hash=?,stamp=?,checked_at=?,debt_usd=?,hf=? WHERE account=?',values)
        self.store.set_meta('universe_job',{'state':'idle','last_batch':len(values),'block':block,'finished_at':time.time()})

    def selected(self,limit):
        self.discover()
        # Reserve half for oldest coherent position checks; the other half for
        # highest observed risk. Coherent models still re-read every selected wallet.
        with self.store.db() as c:
            recent=self.store.product('position_rows')
            last=set(recent['payload'].get('wallets',[])) if recent else set()
            active=[r[0] for r in c.execute('SELECT account FROM borrower_census WHERE debt_usd>0 ORDER BY CASE WHEN debt_usd>=1000 AND hf<1.2 THEN 0 ELSE 1 END,hf,debt_usd DESC,account')]
        if limit==0:return active
        high=active[:max(1,limit//2)]
        # Persistent age of position validation prevents risk-only starvation.
        checked=self.store.meta('coherent_wallet_checks',{})
        tail=sorted((a for a in active if a not in high),key=lambda a:(checked.get(a,0),a))
        return (high+tail)[:limit]

    def status(self):
        self.discover();head=self.store.meta('head');now=time.time()
        clock=head['stamp']+max(0,now-head['observed_at']) if head else now
        with self.store.db() as c:
            r=c.execute('''SELECT count(*),count(stamp),sum(CASE WHEN stamp>=? THEN 1 ELSE 0 END),
              sum(CASE WHEN debt_usd>0 THEN 1 ELSE 0 END),min(stamp),max(stamp),sum(debt_usd)
              FROM borrower_census''',(clock-self.freshness,)).fetchone()
        total,scanned,fresh,active,oldest,newest,debt=r
        return {'known_wallets':total,'scanned_wallets':scanned,'fresh_wallets':fresh or 0,
          'scanned_fraction':scanned/total if total else None,'fresh_fraction':(fresh or 0)/total if total else None,
          'active_observed_wallets':active or 0,'oldest_source_stamp':oldest,'newest_source_stamp':newest,
          'rolling_observed_debt_usd':debt,'synchronous_snapshot':False,'full_market_coverage':False,
          'freshness_seconds':self.freshness,'seed':self.store.meta('universe_seed'),
          'discovery_gap_closed':self.store.meta('discovery_progress',{}).get('state')=='completed' and self.store.meta('universe_seed',{}).get('history_complete',False),
          'discovery':self.store.meta('discovery_progress',{'state':'pending'}),'job':self.store.meta('universe_job',{'state':'starting'}),
          'note':'Rolling census has mixed block times; observed debt is not a synchronous market total or a debt-coverage denominator.'}


def universe_loop(scanner,stop,interval):
    while not stop.is_set():
        scanner.store.set_meta('universe_job',{'state':'running','started_at':time.time()})
        try:scanner.scan()
        except Exception as exc:
            scanner.store.set_meta('universe_job',{'state':'error','kind':getattr(exc,'kind',type(exc).__name__),'error':str(exc)[:180],'at':time.time()})
        stop.wait(interval)


def discovery_loop(scanner,stop):
    """Fill only missing Borrow discovery between audited seed and live tail.

This does not pretend that all historical event types have been backfilled.
"""
    from defi_data.pipeline import ROOT
    from defi_data.evm import parse_events,decode_event
    from defi_data.rpc import Rpc
    rpc=Rpc(scanner.store.folder/'discovery_rpc',use_cache=False,timeout=10,retry_attempts=1)
    spec=parse_events((ROOT/'data/sources/IPool.sol').read_text(encoding='utf8'))['Borrow']
    chunk=1000
    while not stop.is_set():
        seed=scanner.store.meta('universe_seed',{});start=scanner.store.meta('start_block');end=seed.get('end_block')
        if start is None or end is None:stop.wait(5);continue
        progress=scanner.store.meta('discovery_progress',{});lo=progress.get('next_block',end+1);target=start-1
        if lo>target:
            scanner.store.set_meta('discovery_progress',dict(progress,state='completed',next_block=lo,target=target));return
        hi=min(target,lo+chunk-1)
        try:
            before=rpc.one('eth_getBlockByNumber',[hex(hi),False],cache=False)
            logs=rpc.logs(CONTRACTS['aave_v3'][0],[spec['topic']],lo,hi)
            after=rpc.one('eth_getBlockByNumber',[hex(hi),False],cache=False)
            if before['hash']!=after['hash']:raise ValueError('Discovery chunk reorg')
            wallets=sorted({decode_event(log,spec)['onBehalfOf'].lower() for log in logs})
            with scanner.store.db() as c:
                c.executemany('INSERT OR IGNORE INTO borrower_census(account,source) VALUES (?,?)',[(a,'Borrow_discovery_gap') for a in wallets])
                value={'state':'completed' if hi==target else 'catching_up','from_block':end+1,'next_block':hi+1,'target':target,
                  'last_chunk_hash':after['hash'],'last_chunk_end':hi,'updated_at':time.time(),
                  'scope':'Borrow discovery only; not full missing event history'}
                c.execute('INSERT OR REPLACE INTO meta VALUES (?,?)',('discovery_progress',json.dumps(value)))
            chunk=min(1000,chunk*2)
        except Exception as exc:
            scanner.store.set_meta('discovery_progress',dict(progress,state='error',next_block=lo,target=target,error_kind=getattr(exc,'kind',type(exc).__name__),updated_at=time.time()))
            chunk=max(20,chunk//2)
        stop.wait(2 if hi<target else 1)
