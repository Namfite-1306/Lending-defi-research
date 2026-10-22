"""Full observed borrower cohort at a fixed pre-stress block, sparse position reads."""
import json,csv
from decimal import Decimal as D
from collections import defaultdict
from .recovery import RUN,OUT,database,merge_ranges
from .pipeline import ROOT,CONTRACTS,call,call_request,registry,metadata,csv_write,save_json
from .expansion import read_csv,protocol_hf,risk_debt_raw
from .evm import words,uint,addr,address_array
from .rpc import Rpc

BLOCK=21762264
def main():
    folder=RUN/'full_snapshot_21762264';folder.mkdir(parents=True,exist_ok=True)
    rpc=Rpc(ROOT/'data/rpc_cache',batch_size=200,multicall=True,cache_individual=False)
    c=database();bounds=json.loads((RUN/'block_range.json').read_text(encoding='utf8'))
    covered=merge_ranges(list(c.execute("SELECT lo,hi FROM ranges WHERE protocol='aave_v3'")))
    if not any(a<=bounds['start_block'] and b>=BLOCK for a,b in covered):raise ValueError('Complete Aave borrower history up to snapshot required')
    wallets=[r[0] for r in c.execute("SELECT DISTINCT account FROM events WHERE protocol='aave_v3' AND name='Borrow' AND block<=? ORDER BY account",(BLOCK,))];c.close()
    pool,oracle,provider=registry(rpc,BLOCK);revision=uint(call(rpc,pool,'POOL_REVISION()',[],BLOCK)[0])
    reserves=address_array(rpc.one(*call_request(pool,'getReservesList()',[],BLOCK)));meta=metadata(rpc,reserves,BLOCK)
    cfgs=rpc.many([call_request(provider,'getReserveConfigurationData(address)',[t],BLOCK) for t in reserves])
    reserve=rpc.many([call_request(pool,'getReserveData(address)',[t],BLOCK) for t in reserves])
    rawcfgs=rpc.many([call_request(pool,'getConfiguration(address)',[t],BLOCK) for t in reserves])
    prices=rpc.many([call_request(oracle,'getAssetPrice(address)',[t],BLOCK) for t in reserves]);base=D(uint(call(rpc,oracle,'BASE_CURRENCY_UNIT()',[],BLOCK)[0]))
    indexes=rpc.many([call_request(pool,'getReserveNormalizedVariableDebt(address)',[t],BLOCK) for t in reserves])
    for t,co,re,ra,pr,ind in zip(reserves,cfgs,reserve,rawcfgs,prices,indexes):
        w=words(co);m=meta[t];m.update(lt=D(uint(w[2]))/10000,price=D(uint(words(pr)[0]))/base,
          reserve_id=uint(words(re)[7]),category=(uint(words(ra)[0])>>168)&255,debt_index=uint(words(ind)[0]))
    categories={};total_active=0;total_passed=0;debt_total=D(0);failed_debt=D(0)
    checks=[];positions=[];resume=0
    if (folder/'scope.json').exists():
        prior=json.loads((folder/'scope.json').read_text(encoding='utf8'))
        prior_checks=read_csv(folder/'validation.csv');prior_positions=read_csv(folder/'positions.csv')
        if (prior.get('historical_borrowers')==len(wallets) and len(prior_checks)==prior.get('active_debt_wallets')
            and prior_positions and all('hf_debt_raw' in r for r in prior_positions) and all(r['passed']=='True' for r in prior_checks)):
            checks=prior_checks;positions=prior_positions;resume=prior['wallets_scanned'];total_active=prior['active_debt_wallets'];total_passed=prior['passed']
            debt_total=D(prior['reported_debt_usd']);failed_debt=D(prior['failed_debt_usd'])
    for start in range(resume,len(wallets),200):
        group=wallets[start:start+200]
        accounts=rpc.many([call_request(pool,'getUserAccountData(address)',[a],BLOCK) for a in group])
        active=[(a,words(r)) for a,r in zip(group,accounts) if uint(words(r)[1])>0]
        active_wallets=[a for a,_ in active]
        states=rpc.many([call_request(pool,sig,[a],BLOCK) for a in active_wallets for sig in ('getUserConfiguration(address)','getUserEMode(address)')])
        configs={a:(uint(words(states[i*2])[0]),uint(words(states[i*2+1])[0])) for i,a in enumerate(active_wallets)}
        for mode in sorted({v[1] for v in configs.values()}-{0}):
            if mode in categories:continue
            w=call(rpc,pool,'getEModeCategoryData(uint8)',[mode],BLOCK)
            if uint(w[0])!=32:raise ValueError('Unknown category ABI')
            w=w[1:]
            if addr(w[3])!='0x'+'0'*40:raise ValueError('Custom E-mode price source adapter required')
            bitmap=rpc.many([call_request(pool,'getEModeCategoryCollateralBitmap(uint8)',[mode],BLOCK)],allow_errors=True)[0]
            categories[mode]={'lt':D(uint(w[1]))/10000,'bitmap':uint(words(bitmap)[0]) if isinstance(bitmap,str) else None}
        refs=[]
        for a,_ in active:
            bitmap,mode=configs[a]
            for t in reserves:
                if (bitmap>>(2*meta[t]['reserve_id']))&3:refs.append((a,t,mode))
        balances=rpc.many([call_request(provider,'getUserReserveData(address,address)',[t,a],BLOCK) for a,t,mode in refs])
        local=defaultdict(list)
        for (a,t,mode),raw in zip(refs,balances):
            w=words(raw)
            if len(w)!=9:raise ValueError('Unknown provider ABI')
            m=meta[t];s=uint(w[0]);repay=uint(w[1])+uint(w[2]);d=risk_debt_raw(uint(w[1]),uint(w[4]),m['debt_index'],revision)
            enabled=bool(uint(w[8]));lt=m['lt'];unit=10**m['decimals'];price=int(m['price']*base)
            if mode:
                cat=categories[mode];eligible=bool(cat['bitmap']&(1<<m['reserve_id'])) if cat['bitmap'] is not None else m['category']==mode
                if eligible:lt=cat['lt']
            cv=D(s*price//unit)/base if enabled and (m['lt']>0 or revision>=10) else D(0)
            dv=D((d*price+(unit-1 if revision>=9 else 0))//unit)/base
            local[a].append({'account':a,'block':BLOCK,'token':t,'symbol':m['symbol'],'decimals':m['decimals'],'supply_raw':str(s),'debt_raw':str(d),
              'collateral_enabled':enabled,'emode':mode,'effective_lt':str(lt),'price_usd':str(m['price']),'collateral_usd':str(cv),'debt_usd':str(dv),
              'pool_revision':revision,'hf_debt_raw':str(d),'repayable_debt_raw':str(repay),
              'repayable_debt_usd':str(D(repay)/unit*m['price']),
              'selection':'all Borrow.onBehalfOf before block; include only positive debt at block'})
        for a,reported in active:
            rows=local[a];collateral=sum(D(r['collateral_usd']) for r in rows);debt=sum(D(r['debt_usd']) for r in rows)
            weighted=sum(D(r['collateral_usd'])*D(r['effective_lt']) for r in rows)
            expected_c=D(uint(reported[0]))/base;expected_d=D(uint(reported[1]))/base;expected_hf=D(uint(reported[5]))/10**18
            hf=protocol_hf(collateral,weighted,debt,base,revision)
            errors=[abs(collateral-expected_c)/max(expected_c,D(1)),abs(debt-expected_d)/max(expected_d,D(1))]
            if hf is not None:errors.append(abs(hf-expected_hf)/max(expected_hf,D(1)))
            else:errors.append(D(1))
            passed=max(errors)<=D('.0001');total_active+=1;total_passed+=passed;debt_total+=expected_d
            if not passed:failed_debt+=expected_d
            checks.append({'account':a,'block':BLOCK,'debt_reported_usd':str(expected_d),'hf_reported':str(expected_hf),'hf_calculated':str(hf),
                           'max_relative_error':str(max(errors)),'passed':passed,'emode':configs[a][1]})
            for r in rows:r['validation_passed']=passed
            positions+=rows
        csv_write(folder/'positions.csv',positions);csv_write(folder/'validation.csv',checks)
        save_json(folder/'scope.json',{'block':BLOCK,'pool':pool,'oracle':oracle,'provider':provider,'pool_revision':revision,
            'historical_borrowers':len(wallets),'wallets_scanned':min(start+200,len(wallets)),'active_debt_wallets':total_active,
            'passed':total_passed,'reported_debt_usd':str(debt_total),'failed_debt_usd':str(failed_debt),'borrower_history_complete':True,
            'full_snapshot_complete':start+200>=len(wallets),'timing':'block end before pilot stress begins','all_market_dates':False})
        print(f'B FULL scanned {min(start+200,len(wallets))}/{len(wallets)}, active={total_active}, passed={total_passed}',flush=True)
    csv_write(folder/'reserve_metadata.csv',[{'token':t,**m} for t,m in meta.items()])
if __name__=='__main__':main()
