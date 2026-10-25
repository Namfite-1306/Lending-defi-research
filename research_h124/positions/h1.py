"""Quarter-end full borrower census with sparse batched historical state reads."""
import argparse,json,sqlite3,time
from collections import defaultdict
from decimal import Decimal as D
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from defi_data.rpc import Rpc,RpcError
from defi_data.pipeline import call,call_request,registry,metadata,ZERO
from defi_data.evm import words,uint,addr,address_array
from defi_data.expansion import protocol_hf,risk_debt_raw,clipped_coverage
from defi_models.core import Data,DEFAULTS,Portfolio
from defi_models.statistics import breakpoint
from .common import SOURCE,DATA,OUT,read,write,save,digest,connect,now,worker_lock

GHO='0x40d16fc0246ad3160ccc09b8d0d3a2cd28ae6c2f'

def historical_risk_debt(token,revision,stable,scaled,index,repayable):
    indexed=risk_debt_raw(stable,scaled,index,revision)
    # v3.3 / Ethereum Pool revision 7 fixes GenericLogic to use vGHO.balanceOf,
    # which includes the user's legacy discount. totalSupply remains undiscounted.
    return (repayable if token==GHO and revision>=7 else indexed),indexed


def quarters():
    return [(f'{y}Q{q}',datetime(y+(q==4),1 if q==4 else q*3+1,1,tzinfo=timezone.utc)) for y in range(2023,2027) for q in range(1,5) if (y,q)<=(2026,3)]

def plan(source=SOURCE,out=DATA/'h1'):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);path=out/'quarter_plan.json'
    if path.exists():return json.loads(path.read_text(encoding='utf8'))
    bounds=json.loads((source/'block_range.json').read_text());rpc=Rpc(out/'rpc',batch_size=100,multicall=True,timeout=12,retry_attempts=1)
    dataset=Data(source,DEFAULTS);seed=dataset.read('borrower_universe.csv')
    rows=[]
    for name,at in quarters():
        block=rpc.block_at(int(at.timestamp()),bounds['end_block']+1)-1;header=rpc.block(block)
        rows.append({'quarter':name,'cutoff_exclusive_utc':at.isoformat(),'block':block,'hash':header['hash'],'stamp':int(header['timestamp'],16),
          'historical_borrowers':sum(int(r['first_borrow_block'])<=block for r in seed),'status':'pending'})
        print('H1 planned',name,block,rows[-1]['historical_borrowers'],flush=True)
    save(path,rows);return rows


class State:
    def __init__(self,rpc,block):
        self.rpc=rpc;self.block=block;self.pool,self.oracle,self.provider=registry(rpc,block)
        self.revision=uint(call(rpc,self.pool,'POOL_REVISION()',[],block)[0])
        if not 1<=self.revision<=11:raise ValueError('Unreviewed historical Pool revision')
        self.tokens=address_array(rpc.one(*call_request(self.pool,'getReservesList()',[],block)))
        self.meta=metadata(rpc,self.tokens,block);self.base=D(uint(call(rpc,self.oracle,'BASE_CURRENCY_UNIT()',[],block)[0]));self.categories={}
        for sig,key in [('getReserveConfigurationData(address)','config'),('getReserveData(address)','reserve')]:
            target=self.provider if key=='config' else self.pool
            results=rpc.many([call_request(target,sig,[t],block) for t in self.tokens])
            for t,v in zip(self.tokens,results):self.meta[t][key]=words(v)
        raw=rpc.many([call_request(self.pool,'getConfiguration(address)',[t],block) for t in self.tokens])
        prices=rpc.many([call_request(self.oracle,'getAssetPrice(address)',[t],block) for t in self.tokens])
        indices=rpc.many([call_request(self.pool,'getReserveNormalizedVariableDebt(address)',[t],block) for t in self.tokens])
        for t,r,p,i in zip(self.tokens,raw,prices,indices):
            m=self.meta[t];m.update(lt=D(uint(m['config'][2]))/10000,category=(uint(words(r)[0])>>168)&255,
              reserve_id=uint(m['reserve'][7]),debt_index=uint(words(i)[0]),price_raw=uint(words(p)[0]),
              configuration_word=str(uint(words(r)[0])),ltv=D(uint(m['config'][1]))/10000,liquidation_bonus_factor=D(uint(m['config'][3]))/10000)
    def category(self,mode):
        if mode in self.categories:return self.categories[mode]
        w=call(self.rpc,self.pool,'getEModeCategoryData(uint8)',[mode],self.block)
        if uint(w[0])!=32:raise ValueError('Unknown E-mode return layout')
        w=w[1:]
        if addr(w[3])!=ZERO:raise ValueError('Custom E-mode oracle pricing requires explicit adapter; no approximation used')
        try:bitmap=uint(call(self.rpc,self.pool,'getEModeCategoryCollateralBitmap(uint8)',[mode],self.block)[0])
        except RpcError as exc:
            if self.revision>=6 or exc.kind!='rpc_error' or 'revert' not in str(exc).lower():raise
            bitmap=None
        self.categories[mode]={'lt':D(uint(w[1]))/10000,'bitmap':bitmap,'ltv':D(uint(w[0]))/10000,'liquidation_bonus_factor':D(uint(w[2]))/10000,'price_source':addr(w[3])};return self.categories[mode]
    def batch(self,accounts):
        reported=self.rpc.many([call_request(self.pool,'getUserAccountData(address)',[a],self.block) for a in accounts])
        if len(reported)!=len(accounts):raise ValueError('Incomplete account responses')
        active=[(a,words(r)) for a,r in zip(accounts,reported) if uint(words(r)[1])>0]
        states=self.rpc.many([call_request(self.pool,sig,[a],self.block) for a,_ in active for sig in ['getUserConfiguration(address)','getUserEMode(address)']]) if active else []
        configs={a:(uint(words(states[2*i])[0]),uint(words(states[2*i+1])[0])) for i,(a,_) in enumerate(active)}
        refs=[]
        for a,_ in active:
            bits,mode=configs[a]
            if mode:self.category(mode)
            refs.extend((a,t,mode) for t in self.tokens if (bits>>(2*self.meta[t]['reserve_id']))&3)
        balances=self.rpc.many([call_request(self.provider,'getUserReserveData(address,address)',[t,a],self.block) for a,t,mode in refs]) if refs else []
        positions=defaultdict(list)
        for (a,t,mode),result in zip(refs,balances):
            w=words(result)
            if len(w)!=9:raise ValueError('Unknown reserve balance ABI')
            m=self.meta[t];s=uint(w[0]);repay=uint(w[1])+uint(w[2]);risk,indexed=historical_risk_debt(t,self.revision,uint(w[1]),uint(w[4]),m['debt_index'],repay)
            cat=self.categories.get(mode);lt=m['lt']
            if cat and (bool(cat['bitmap']&(1<<m['reserve_id'])) if cat['bitmap'] is not None else m['category']==mode):lt=cat['lt']
            enabled=bool(uint(w[8]));unit=10**m['decimals'];price=m['price_raw']
            cv=D(s*price//unit)/self.base if enabled and (m['lt']>0 or self.revision>=10) else D(0)
            dv=D((risk*price+(unit-1 if self.revision>=9 else 0))//unit)/self.base
            positions[a].append(dict(account=a,block=self.block,token=t,symbol=m['symbol'],decimals=m['decimals'],
              supply_raw=str(s),debt_raw=str(risk),hf_debt_raw=str(risk),repayable_debt_raw=str(repay),indexed_debt_raw=str(indexed),
              repayable_debt_usd=str(D(repay)*price/unit/self.base),collateral_enabled=enabled,emode=mode,
              effective_lt=str(lt),price_usd=str(D(price)/self.base),collateral_usd=str(cv),debt_usd=str(dv),pool_revision=self.revision))
        checks={}
        for a,r in active:
            ps=positions[a];coll=sum((D(x['collateral_usd']) for x in ps),D(0));debt=sum((D(x['debt_usd']) for x in ps),D(0))
            weighted=sum((D(x['collateral_usd'])*D(x['effective_lt']) for x in ps),D(0));hf=protocol_hf(coll,weighted,debt,self.base,self.revision)
            ec=D(uint(r[0]))/self.base;ed=D(uint(r[1]))/self.base;eh=D(uint(r[5]))/10**18
            errors=[abs(coll-ec)/max(ec,D(1)),abs(debt-ed)/max(ed,D(1)),abs(hf-eh)/max(abs(eh),D('1e-12')) if hf is not None else D(1)]
            passed=max(errors)<=D('.0001');checks[a]=dict(account=a,block=self.block,hf_reported=str(eh),hf_calculated=str(hf),debt_reported_usd=str(ed),max_relative_error=str(max(errors)),passed=passed)
            for row in ps:row['validation_passed']=passed
        failed=[v for v in checks.values() if not v['passed']]
        if failed:
            error=ValueError('Historical HF reconciliation failed; no batch committed')
            error.reconciliation=failed;error.positions=[p for r in failed for p in positions[r['account']]]
            raise error
        return [(a,str(D(uint(words(r)[1]))/self.base),checks.get(a,{}),positions.get(a,[])) for a,r in zip(accounts,reported)]


def aggregate_check(state,positions,wallet_count):
    totals=defaultdict(int);risk_totals=defaultdict(int)
    for r in positions:
        totals[r['token']]+=int(r['repayable_debt_raw']);risk_totals[r['token']]+=int(r.get('indexed_debt_raw',r['debt_raw']))
    addresses=state.rpc.many([call_request(state.provider,'getReserveTokensAddresses(address)',[t],state.block) for t in state.tokens]);requests=[];refs=[]
    for t,raw in zip(state.tokens,addresses):
        w=words(raw)
        for word in w[1:3]:
            token=addr(word)
            if token!=ZERO:requests.append(call_request(token,'totalSupply()',[],state.block));refs.append(t)
    values=state.rpc.many(requests);expected=defaultdict(int)
    for t,raw in zip(refs,values):expected[t]+=uint(words(raw)[0])
    checks=[]
    for t in state.tokens:
        gho=t=='0x40d16fc0246ad3160ccc09b8d0d3a2cd28ae6c2f'
        comparable=risk_totals[t] if gho else totals[t]
        diff=abs(comparable-expected[t]);tolerance=max(wallet_count*2,int(expected[t]*D('.0001')))
        checks.append(dict(token=t,borrower_sum_raw=str(comparable),repayable_borrower_sum_raw=str(totals[t]),risk_borrower_sum_raw=str(risk_totals[t]),
          comparison_basis='GHO undiscounted indexed debt; token totalSupply excludes user discounts' if gho else 'repayable debt',
          debt_token_supply_raw=str(expected[t]),absolute_error_raw=str(diff),tolerance_raw=str(tolerance),passed=diff<=tolerance))
    return checks


def run(source=SOURCE,out=DATA/'h1',minutes=120,batch=200,max_batches=None):
    with worker_lock(Path(out)/'collector.lock'):
        return collect(source,out,minutes,batch,max_batches)

def collect(source=SOURCE,out=DATA/'h1',minutes=120,batch=200,max_batches=None):
    source=Path(source);out=Path(out);items=plan(source,out);deadline=time.monotonic()+minutes*60
    for item in items:
        file=out/item['quarter']/'scope.json'
        if file.exists():
            scope=json.loads(file.read_text())
            if scope.get('status')=='collecting' and not scope.get('full_snapshot_complete'):
                scope.update(status='partial_checkpoint',previous_worker_interrupted=True);save(file,scope)
    dataset=Data(source,DEFAULTS);seed=dataset.read('borrower_universe.csv');bounds=json.loads((source/'block_range.json').read_text())
    c=connect(source);ranges=list(c.execute("SELECT lo,hi FROM ranges WHERE protocol='aave_v3'"));c.close()
    for item in items:
        if time.monotonic()>=deadline:break
        folder=out/item['quarter'];folder.mkdir(parents=True,exist_ok=True);block=item['block'];status=dict(item,updated_utc=now(),full_snapshot_complete=False)
        try:
            covered=clipped_coverage(ranges,bounds['start_block'],block)
            if covered!=[[bounds['start_block'],block]]:raise ValueError('Borrow history coverage incomplete')
            wallets=sorted(r['account'] for r in seed if int(r['first_borrow_block'])<=block)
            if not all(r['history_complete']=='True' for r in seed):raise ValueError('Seed history not audited complete')
            prior_file=folder/'scope.json'
            if prior_file.exists():
                prior=json.loads(prior_file.read_text())
                if prior.get('full_snapshot_complete') and prior.get('aggregate_adapter_version')==2 and prior.get('snapshot_schema_version')==3 and prior.get('hash')==item['hash'] and prior.get('historical_borrowers')==len(wallets):
                    freeze=json.loads((folder/'freeze_manifest.json').read_text())
                    if all(digest(folder/name)==value for name,value in freeze['files'].items()):
                        print('H1 verified complete checkpoint',item['quarter'],flush=True);continue
            rpc=Rpc(out/'rpc',batch_size=400,multicall=True,cache_individual=False,timeout=15,retry_attempts=1)
            if rpc.block(block)['hash']!=item['hash']:raise ValueError('Cutoff hash mismatch')
            db=sqlite3.connect(folder/'snapshot.sqlite',timeout=30);db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS accounts(account TEXT PRIMARY KEY,debt TEXT,checks TEXT,positions TEXT)')
            done={r[0] for r in db.execute('SELECT account FROM accounts')}
            if not done.issubset(set(wallets)):raise ValueError('Checkpoint cohort identity mismatch')
            pending=[a for a in wallets if a not in done];state=State(rpc,block);n=0
            status.update(status='collecting',pool_revision=state.revision,pool=state.pool,oracle=state.oracle,provider=state.provider,
              borrower_history_complete=True,seed_sha256=digest(source/'processed/borrower_universe.csv'),wallets_scanned=len(done),
              timing='quarter-end block; all prior Borrow cohort; no future liquidation selection')
            save(folder/'scope.json',status)
            for start in range(0,len(pending),batch):
                if time.monotonic()>=deadline or (max_batches is not None and n>=max_batches):break
                values=state.batch(pending[start:start+batch])
                with db:db.executemany('INSERT INTO accounts VALUES (?,?,?,?)',[(a,d,json.dumps(ch),json.dumps(ps)) for a,d,ch,ps in values])
                n+=1;status.update(wallets_scanned=db.execute('SELECT count(*) FROM accounts').fetchone()[0],updated_utc=now())
                status['active_debt_wallets']=db.execute("SELECT count(*) FROM accounts WHERE debt<>'0'").fetchone()[0]
                save(folder/'scope.json',status);print('H1',item['quarter'],status['wallets_scanned'],'/',len(wallets),flush=True)
            if status['wallets_scanned']==len(wallets):
                records=list(db.execute('SELECT debt,checks,positions FROM accounts ORDER BY account'));checks=[json.loads(ch) for d,ch,ps in records if D(d)>0]
                positions=[r for d,ch,ps in records for r in json.loads(ps)];agg=aggregate_check(state,positions,len(wallets))
                p=Portfolio(positions,DEFAULTS);actual,_=p.stress();reported=np.array([float(ch['hf_reported']) for ch in checks])
                model_ok=bool(np.all(np.abs(actual-reported)/np.maximum(np.abs(reported),1e-12)<=1e-4))
                status.update(passed=sum(ch['passed'] for ch in checks),active_debt_wallets=len(checks),model_hf_passed=model_ok,
                  aggregate_debt_passed=all(r['passed'] for r in agg),aggregate_adapter_version=2,snapshot_schema_version=3,reported_debt_usd=str(sum((D(d) for d,ch,ps in records),D(0))))
                status['full_snapshot_complete']=status['passed']==len(checks) and model_ok and status['aggregate_debt_passed']
                status['status']='completed' if status['full_snapshot_complete'] else 'reconciliation_failed'
                write(folder/'positions.csv',positions);write(folder/'validation.csv',checks);write(folder/'aggregate_debt_validation.csv',agg)
                write(folder/'reserve_metadata.csv',[dict(token=t,**{k:str(v) for k,v in m.items() if k not in ['config','reserve']}) for t,m in state.meta.items()])
                for mode in sorted({int(r['emode']) for r in positions}-{0}):state.category(mode)
                save(folder/'emode_categories.json',{str(k):v for k,v in state.categories.items()})
                slot='0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc'
                implementation=addr(rpc.one('eth_getStorageAt',[state.pool,slot,hex(block)]));code=rpc.one('eth_getCode',[implementation,hex(block)])
                save(folder/'implementation.json',{'address':implementation,'bytecode_sha256':__import__('hashlib').sha256(bytes.fromhex(code[2:])).hexdigest(),'block':block,'pool_revision':state.revision})
                if status['full_snapshot_complete']:
                    save(folder/'freeze_manifest.json',{'created_utc':now(),'block':block,'block_hash':item['hash'],'code_sha256':digest(__file__),
                      'files':{name:digest(folder/name) for name in ['positions.csv','validation.csv','aggregate_debt_validation.csv','reserve_metadata.csv','emode_categories.json','implementation.json']},
                      'scope':'full borrower risk snapshot; interface reconciliation, not independent-provider validation'})
            else:status['status']='partial_checkpoint'
            db.close();save(folder/'scope.json',status)
        except Exception as exc:
            if hasattr(exc,'reconciliation'):
                write(folder/'failed_reconciliation.csv',exc.reconciliation)
                write(folder/'failed_positions.csv',exc.positions)
            status.update(status='error',error_kind=getattr(exc,'kind',type(exc).__name__),error=str(exc)[:400]);save(folder/'scope.json',status)
            print('H1 ERROR',item['quarter'],status['error'],flush=True)
    summary(out)


def summary(folder=DATA/'h1'):
    folder=Path(folder);items=json.loads((folder/'quarter_plan.json').read_text());result=[]
    for item in items:
        file=folder/item['quarter']/'scope.json';result.append(json.loads(file.read_text()) if file.exists() else item)
    save(folder/'progress.json',{'updated_utc':now(),'required_snapshots':len(items),'full_snapshots':sum(r.get('full_snapshot_complete') is True for r in result),'snapshots':result})
    return result


def stress(folder=DATA/'h1',out=OUT/'h1'):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);curves=[];breaks=[];ready=[]
    for scope in summary(folder):
        if not scope.get('full_snapshot_complete'):continue
        root=Path(folder)/scope['quarter'];p=Portfolio(read(root/'positions.csv'),DEFAULTS);ready.append(scope['quarter'])
        for scenario,eth,btc in [('ETH_only',1,0),('BTC_only',0,1),('joint',1,1)]:
            series=[]
            for shock in np.linspace(0,.6,61):
                hf,debt=p.stress(shock*eth,shock*btc);eligible=hf<1
                row=dict(quarter=scope['quarter'],block=scope['block'],scenario=scenario,shock=float(shock),wallets=len(hf),eligible_wallets=int(eligible.sum()),
                  eligible_debt_usd=float(debt[eligible].sum()),total_debt_usd=float(debt.sum()),eligible_debt_share=float(debt[eligible].sum()/debt.sum()))
                curves.append(row);series.append(row)
            fit=breakpoint([r['shock'] for r in series],[r['eligible_debt_share'] for r in series]);delta=np.diff([r['eligible_debt_usd'] for r in series]);j=int(delta.argmax())
            breaks.append(dict(quarter=scope['quarter'],scenario=scenario,share_knot=fit.get('knot'),largest_usd_jump_from=series[j]['shock'],largest_usd_jump_to=series[j+1]['shock'],largest_usd_jump=float(delta[j])))
    write(out/'stress_curves.csv',curves);write(out/'breakpoints.csv',breaks)
    save(out/'summary.json',{'updated_utc':now(),'complete_quarters':ready,'full_snapshots':len(ready),'required':15,'status':'complete_scoped' if len(ready)==15 else 'partial',
      'limitations':['Static counterfactual eligible debt, not executed volume','Grid points are not independent observations','Derivative factors are one-to-one approximations','Quarter-end snapshots are not pre-event snapshots']})

def main():
    p=argparse.ArgumentParser();p.add_argument('--minutes',type=float,default=120);p.add_argument('--batch',type=int,default=200);p.add_argument('--stress-only',action='store_true');p.add_argument('--max-batches',type=int);a=p.parse_args()
    if not 0<a.minutes<=1440 or not 1<=a.batch<=500:p.error('Invalid collection limits')
    if not a.stress_only:run(minutes=a.minutes,batch=a.batch,max_batches=a.max_batches)
    from .h1_analysis import run as analyze
    analyze()
if __name__=='__main__':main()
