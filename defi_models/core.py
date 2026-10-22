import csv,hashlib,json,math,sqlite3
from pathlib import Path
from datetime import datetime,timezone
from collections import defaultdict
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_RUN=ROOT/'data/runs/recovery_20261020'
DEFAULTS={
 'snapshot':'full_snapshot_21762264','shock_step':0.01,'shock_max':0.60,
 'eth_symbols':['WETH','wstETH','rETH','cbETH','weETH','osETH','ETHx','rsETH'],
 'btc_symbols':['WBTC','tBTC','cbBTC','LBTC'],
 'derivative_mapping':'one_to_one_factor_sensitivity_not_peg_estimate',
 'recursive_window_hours':24,'recursive_label':'temporal','outcome_days':7,'match_caliper':0.75,
 'protocol':'aave_v3','train_fraction':0.8,'hawkes_half_lives_hours':[1/60,1/12,0.5,2,6],
 'bootstrap_repetitions':300,'seed':42,
 'cascade_shocks':[0.1,0.2,0.3],'liquidity_depth_usd':100000000,
 'impact_coefficient':0.05,'impact_cap':0.8,'oracle_pass_through':1.0,
 'close_factor':0.5,'liquidation_bonus':0.05,'gas_usd':20,
 'max_rounds':20,'sell_fraction':1.0,
 'policy_close_factors':[0.25,0.5,1.0], 'policy_bonuses':[0.03,0.05,0.08],
 'policy_lt_shifts':[-0.03,0.0,0.03],
}

def stamp(value):
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:raise ValueError('Timestamp must include UTC offset')
    return parsed.timestamp()
def iso(value):return datetime.fromtimestamp(value,timezone.utc).isoformat()
def rows(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:yield from csv.DictReader(f)
def write_csv(path,data,fields=None):
    data=list(data);fields=fields or (list(data[0]) if data else ['status'])
    with Path(path).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(data)
def clean(value):
    if isinstance(value,dict):return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [clean(v) for v in value]
    if isinstance(value,np.ndarray):return clean(value.tolist())
    if isinstance(value,np.generic):return clean(value.item())
    if isinstance(value,float) and not math.isfinite(value):return None
    return value
def write_json(path,value):Path(path).write_text(json.dumps(clean(value),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda:f.read(8*1024*1024),b''):h.update(part)
    return h.hexdigest()
def require(condition,message):
    if not condition:raise ValueError(message)

def shock_grid(maximum,step):
    require(0<step<=maximum<1,'Invalid shock grid')
    return np.unique(np.append(np.arange(0,maximum,step),maximum))

class Data:
    def __init__(self,run,cfg):
        self.run=Path(run);self.p=self.run/'processed';self.cfg=cfg;self.used=set();self.checked=set()
        manifest=self.run/'freeze_manifest.json'
        require(manifest.exists(),'Missing freeze_manifest.json; run data audit 3 first')
        self.used.add(manifest)
        self.used.update(p for p in self.run.glob('audit_*_*.json'))
        if (self.run/'block_range.json').exists():self.used.add(self.run/'block_range.json')
        self.frozen={str(Path(r['file'].replace('\\','/'))):r['sha256'] for r in json.loads(manifest.read_text(encoding='utf8'))['csv_files']}
    def verify(self,path):
        if path in self.checked:return
        key=str(path.relative_to(self.run));expected=self.frozen.get(key)
        require(expected is not None,f'Input not in data freeze manifest: {key}; audit the new dataset first')
        require(sha(path)==expected,f'Input hash changed: {key}; investigate and rerun data audit before models')
        self.checked.add(path)
    def path(self,name):
        path=self.p/name;require(path.is_file(),f'Missing input: {path}');self.verify(path);self.used.add(path);return path
    def read(self,name):return list(rows(self.path(name)))
    def snapshot(self):
        path=self.run/self.cfg['snapshot'];scopepath=path/'scope.json'
        require(scopepath.exists(),f'Missing snapshot scope: {scopepath}')
        scope=json.loads(scopepath.read_text(encoding='utf8'));self.used.add(scopepath)
        require(scope.get('full_snapshot_complete'), 'Snapshot incomplete; finish position collection first')
        require(scope.get('passed')==scope.get('active_debt_wallets'),'Snapshot validation failed')
        self.verify(path/'positions.csv');self.used.add(path/'positions.csv');ps=list(rows(path/'positions.csv'))
        require(ps and all(r['validation_passed']=='True' for r in ps),'Position rows must all pass validation')
        require(all(int(r['block'])==scope['block'] for r in ps),'Mixed snapshot blocks')
        require(len({(r['account'],r['token']) for r in ps})==len(ps),'Duplicate wallet-token position rows')
        portfolio=Portfolio(ps,self.cfg)
        require(len(portfolio.accounts)==scope['active_debt_wallets'],'Position universe differs from snapshot scope')
        checks=path/'validation.csv';self.verify(checks);self.used.add(checks);validation=list(rows(checks))
        require(len(validation)==len(portfolio.accounts) and {r['account'] for r in validation}==set(portfolio.accounts),'Validation universe mismatch')
        require(all(r['passed']=='True' and int(r['block'])==scope['block'] and math.isfinite(float(r['max_relative_error'])) and float(r['max_relative_error'])<=1e-4 for r in validation),'Snapshot checks failed')
        actual_hf,_=portfolio.stress();reported=np.array([float(r['hf_reported']) for r in sorted(validation,key=lambda r:r['account'])])
        require(np.all(np.isfinite(reported)) and np.all(np.abs(actual_hf-reported)/np.maximum(np.abs(reported),1e-12)<=1e-4),'Model baseline HF differs from on-chain validation; investigate factor/LT/debt adapter')
        return portfolio,scope
    def connection(self):
        path=self.run/'history.sqlite';require(path.exists(),f'Missing raw event DB: {path}');self.used.add(path)
        return sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
    def snapshot_time(self,block):
        c=self.connection()
        # Last observed timestamp is a conservative cutoff, never a later block.
        r=c.execute('SELECT stamp FROM events WHERE protocol=? AND block<=? ORDER BY block DESC LIMIT 1',('aave_v3',block)).fetchone();c.close()
        require(r is not None,'No historical event before snapshot');return int(r[0])

class Portfolio:
    def __init__(self,records,cfg):
        self.cfg=cfg;self.accounts=sorted({r['account'] for r in records});self.tokens=sorted({r['token'] for r in records})
        ai={a:i for i,a in enumerate(self.accounts)};ti={t:i for i,t in enumerate(self.tokens)}
        shape=(len(ai),len(ti));self.c=np.zeros(shape);self.d=np.zeros(shape);self.repay=np.zeros(shape);self.lt=np.zeros(shape)
        self.symbols=['']*len(ti)
        self.revisions=np.full(len(ai),9,dtype=int)
        for r in records:
            i,j=ai[r['account']],ti[r['token']];self.symbols[j]=r['symbol']
            self.c[i,j]+=float(r['collateral_usd']);self.d[i,j]+=float(r['debt_usd'])
            self.repay[i,j]+=float(r.get('repayable_debt_usd') or r['debt_usd']);self.lt[i,j]=float(r['effective_lt'])
            self.revisions[i]=int(r.get('pool_revision') or 9)
        require(all(np.isfinite(a).all() for a in [self.c,self.d,self.repay,self.lt]),'Non-finite balances/LT')
        require(np.all(self.c>=0) and np.all(self.d>=0) and np.all(self.repay>=0) and np.all((self.lt>=0)&(self.lt<=1)),'Invalid balances/LT')
        self.eth=np.array([s in cfg['eth_symbols'] for s in self.symbols]);self.btc=np.array([s in cfg['btc_symbols'] for s in self.symbols])
        require(not np.any(self.eth & self.btc),'ETH and BTC factor sets overlap')
    def factors(self,eth=0,btc=0):
        require(0<=eth<1 and 0<=btc<1,'Price shock must be in [0,1)')
        return np.where(self.eth,1-eth,np.where(self.btc,1-btc,1.0))
    def stress(self,eth=0,btc=0,lt_shift=0):
        f=self.factors(eth,btc);debt=(self.d*f).sum(axis=1)
        # Integer protocol rounding matters for dust positions as well as revisions.
        # USD notionals are exported in Aave's 1e8 oracle base units.
        hf=np.full_like(debt,np.inf);unit=10**8;wad=10**18
        cv=np.rint(self.c*f*unit);dv=np.rint(self.d*f*unit)
        require(np.max(cv,initial=0)<2**63 and np.max(dv,initial=0)<2**63,'Notional exceeds supported int64 per-asset base units')
        cv=cv.astype(np.int64);dv=dv.astype(np.int64)
        lts=np.rint(np.clip(self.lt+lt_shift,0,1)*10000).astype(np.int64)
        totals=[0]*len(debt);weights=[0]*len(debt);debts=[0]*len(debt)
        for i,j in zip(*np.nonzero(cv)):
            value=int(cv[i,j]);totals[i]+=value;weights[i]+=value*int(lts[i,j])
        for i,j in zip(*np.nonzero(dv)):debts[i]+=int(dv[i,j])
        for i in np.flatnonzero(debt>0):
            raw_d=debts[i];raw_c=totals[i]
            if raw_d<=0:continue
            if self.revisions[i]<9:
                bps=weights[i]//raw_c if raw_c else 0
                adjusted=(raw_c*bps+5000)//10000
                value=(adjusted*wad+raw_d//2)//raw_d
            else:
                raw_weighted=weights[i]
                value=((raw_weighted*wad+raw_d//2)//raw_d)//10000
            hf[i]=value/wad
        return hf,debt
    def mapping(self):return [{'token':t,'symbol':s,'factor':'ETH' if self.eth[j] else 'BTC' if self.btc[j] else 'fixed','collateral_usd':self.c[:,j].sum(),'risk_debt_usd':self.d[:,j].sum()} for j,(t,s) in enumerate(zip(self.tokens,self.symbols))]

def concentration(values):
    x=np.sort(np.asarray(list(values),dtype=float));require(np.all(np.isfinite(x)) and np.all(x>=0),'Non-finite or negative concentration weights')
    if not len(x) or x.sum()==0:return dict(entities=len(x),total=float(x.sum()),hhi=None,gini=None,top1=None,top10=None)
    n=len(x);share=x/x.sum()
    return dict(entities=n,total=x.sum(),hhi=np.sum(share**2),gini=np.sum((2*np.arange(1,n+1)-n-1)*x)/(n*x.sum()),top1=share[-1],top10=share[-10:].sum())

def summary(status,description,limitations,**kw):return dict(status=status,description=description,limitations=limitations,**kw)
