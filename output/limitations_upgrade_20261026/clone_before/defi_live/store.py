import json,sqlite3,time
from pathlib import Path
from contextlib import contextmanager

class Store:
    def __init__(self,folder):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True);self.path=self.folder/'live.sqlite'
        with self.db() as c:
            c.execute('PRAGMA journal_mode=WAL')
            c.executescript('''CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE IF NOT EXISTS blocks (number INTEGER PRIMARY KEY,hash TEXT,parent TEXT,stamp INTEGER);
            CREATE TABLE IF NOT EXISTS events (tx TEXT,idx INTEGER,block INTEGER,protocol TEXT,name TEXT,account TEXT,token TEXT,stamp INTEGER,decoded TEXT,PRIMARY KEY(tx,idx));
            CREATE INDEX IF NOT EXISTS live_event_time ON events(stamp);
            CREATE INDEX IF NOT EXISTS live_event_block ON events(block);
            CREATE INDEX IF NOT EXISTS live_event_account ON events(protocol,account,block);
            CREATE TABLE IF NOT EXISTS products (name TEXT PRIMARY KEY,block INTEGER,hash TEXT,source_stamp INTEGER,built_at REAL,payload TEXT);''')
    @contextmanager
    def db(self):
        c=sqlite3.connect(self.path,timeout=30);c.row_factory=sqlite3.Row
        try:
            with c:yield c
        finally:c.close()
    def meta(self,key,default=None):
        with self.db() as c:r=c.execute('SELECT value FROM meta WHERE key=?',(key,)).fetchone()
        return json.loads(r[0]) if r else default
    def set_meta(self,key,value):
        with self.db() as c:c.execute('INSERT OR REPLACE INTO meta VALUES (?,?)',(key,json.dumps(value)))
    def initialize(self,header,config):
        with self.db() as c:
            prior=c.execute("SELECT value FROM meta WHERE key='config'").fetchone()
            if prior:
                if json.loads(prior[0])!=config:raise ValueError('Live chain config changed; use a different --state-dir')
                return
            c.execute('INSERT INTO blocks VALUES (?,?,?,?)',(header['number'],header['hash'],header['parent'],header['stamp']))
            for k,v in [('cursor',header['number']),('start_block',header['number']+1),('config',config),('created_at',time.time())]:c.execute('INSERT INTO meta VALUES (?,?)',(k,json.dumps(v)))
    def header(self,number):
        with self.db() as c:r=c.execute('SELECT * FROM blocks WHERE number=?',(number,)).fetchone()
        return dict(r) if r else None
    def commit(self,headers,events):
        if not headers:return
        with self.db() as c:
            cur=json.loads(c.execute("SELECT value FROM meta WHERE key='cursor'").fetchone()[0])
            old=c.execute('SELECT hash FROM blocks WHERE number=?',(cur,)).fetchone()
            for h in headers:
                if h['number']!=cur+1 or h['parent']!=old[0]:raise ValueError('Noncontiguous or inconsistent canonical headers')
                c.execute('INSERT INTO blocks VALUES (?,?,?,?)',(h['number'],h['hash'],h['parent'],h['stamp']));cur=h['number'];old=(h['hash'],)
            hashes={h['number']:h['hash'] for h in headers}
            for e in events:
                if e['block'] not in hashes or e['hash']!=hashes[e['block']]:raise ValueError('Log/header mismatch')
                c.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)',(e['tx'],e['idx'],e['block'],e['protocol'],e['name'],e['account'],e['token'],e['stamp'],json.dumps(e['decoded'])))
            c.execute("UPDATE meta SET value=? WHERE key='cursor'",(json.dumps(cur),))
    def rollback(self,ancestor):
        with self.db() as c:
            if not c.execute('SELECT 1 FROM blocks WHERE number=?',(ancestor,)).fetchone():raise ValueError('No local common ancestor')
            c.execute('DELETE FROM events WHERE block>?',(ancestor,));c.execute('DELETE FROM blocks WHERE number>?',(ancestor,))
            c.execute('DELETE FROM products WHERE block>?',(ancestor,));c.execute("UPDATE meta SET value=? WHERE key='cursor'",(json.dumps(ancestor),))
            c.execute('INSERT OR REPLACE INTO meta VALUES (?,?)',('last_reorg',json.dumps({'ancestor':ancestor,'detected_at':time.time()})))
    def publish(self,name,block,block_hash,stamp,payload):
        with self.db() as c:
            row=c.execute('SELECT hash FROM blocks WHERE number=?',(block,)).fetchone()
            if not row or row[0]!=block_hash:raise ValueError('Product belongs to orphaned/uncollected block')
            c.execute('INSERT OR REPLACE INTO products VALUES (?,?,?,?,?,?)',(name,block,block_hash,stamp,time.time(),json.dumps(payload,allow_nan=False)))
    def product(self,name):
        with self.db() as c:r=c.execute('SELECT * FROM products WHERE name=?',(name,)).fetchone()
        if not r:return None
        result=dict(r);result['payload']=json.loads(result['payload']);return result
    def events(self,since=0,limit=20000,protocol=None,until=None):
        sql='SELECT * FROM events WHERE stamp>=?';params=[since]
        if protocol:sql+=' AND protocol=?';params.append(protocol)
        if until is not None:sql+=' AND stamp<=?';params.append(until)
        sql+=' ORDER BY block DESC,idx DESC LIMIT ?';params.append(limit)
        with self.db() as c:rs=c.execute(sql,params).fetchall()
        result=[]
        for r in rs:
            e=dict(r);e['decoded']=json.loads(e['decoded']);result.append(e)
        return result
    def stats(self,since):
        liqs={'aave_v3':'LiquidationCall','compound_v3_usdc':'AbsorbDebt','morpho_blue':'Liquidate'}
        with self.db() as c:
            total=c.execute('SELECT count(*) FROM events WHERE stamp>=?',(since,)).fetchone()[0]
            result=[]
            for p,n in liqs.items():
                r=c.execute('SELECT count(*),count(DISTINCT tx),count(DISTINCT account) FROM events WHERE stamp>=? AND protocol=? AND name=?',(since,p,n)).fetchone()
                result.append({'protocol':p,'liquidation_events':r[0],'transactions':r[1],'borrowers':r[2]})
        return {'all_selected_events':total,'protocols':result}
    def liquidation_groups(self,since,until,protocol):
        name={'aave_v3':'LiquidationCall','compound_v3_usdc':'AbsorbDebt','morpho_blue':'Liquidate'}[protocol]
        with self.db() as c:
            return {r[0]:r[1] for r in c.execute('SELECT account,count(*) FROM events WHERE stamp>=? AND stamp<=? AND protocol=? AND name=? GROUP BY account',(since,until,protocol,name))}
