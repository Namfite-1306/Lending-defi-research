"""Model tables from complete events; explicit units and no imputation of missing prices."""
import argparse,csv,json,calendar
from collections import defaultdict,Counter
from decimal import Decimal as D
from .recovery import RUN,OUT,OLD,database
from .pipeline import ROOT,CONTRACTS,call,call_request,metadata,csv_write,save_json,utc,ts
from .expansion import read_csv
from .evm import words,uint,addr
from .rpc import Rpc
from .price_history import build_price_index,price_before_event

def main():
    OUT.mkdir(parents=True,exist_ok=True);c=database();rpc=Rpc(ROOT/'data/rpc_cache',batch_size=40,multicall=True)
    bounds=json.loads((RUN/'block_range.json').read_text(encoding='utf8'));end=bounds['end_block']
    protocols=bounds.get('protocols',list(CONTRACTS))
    if not protocols or any(p not in CONTRACTS for p in protocols):raise ValueError('Invalid protocol scope')
    coverage=read_csv(OUT/'history_coverage.csv')
    if not coverage or not all(r['download_complete']=='True' for r in coverage):raise ValueError('Complete verified extraction required before model tables')
    # Reject legacy price files before expensive RPC enrichment or CSV rewrites.
    feed=build_price_index(read_csv(OUT/'chainlink_price_updates.csv'))
    # Immutable Morpho market identity may be read at the end; do not treat markets
    # as existing before their first event / creation. Debt accrual still uses each snapshot.
    mids=[r[0] for r in c.execute("SELECT DISTINCT market FROM events WHERE protocol='morpho_blue'")] if 'morpho_blue' in protocols else []
    mr=rpc.many([call_request(CONTRACTS['morpho_blue'][0],'idToMarketParams(bytes32)',[m],end) for m in mids],allow_errors=True)
    markets={};errors=[]
    for mid,r in zip(mids,mr):
        if not isinstance(r,str) or len(words(r))!=5:errors.append({'market':mid,'error':'market identity call failed'});continue
        w=words(r);markets[mid]={'market_id':mid,'loan_token':addr(w[0]),'collateral_token':addr(w[1]),'oracle':addr(w[2]),'irm':addr(w[3]),'lltv':str(D(uint(w[4]))/10**18)}
    csv_write(OUT/'morpho_market_registry_full.csv',list(markets.values()))
    # Contract creation: state binary search distinguishes predeployment NA from an observed zero.
    deployments=[]
    for p in protocols:
        a,_,_=CONTRACTS[p]
        lo,hi=15537394,end
        if rpc.one('eth_getCode',[a,hex(lo)])!='0x':birth=lo;exact=False
        else:
            while lo<hi:
                mid=(lo+hi)//2
                if rpc.one('eth_getCode',[a,hex(mid)])=='0x':lo=mid+1
                else:hi=mid
            birth=lo;exact=True
        stamp=int(rpc.block(birth)['timestamp'],16)
        deployments.append({'protocol':p,'address':a,'deployment_block':birth,'deployment_utc':utc(stamp),'exact_post_merge_search':exact})
    csv_write(OUT/'contract_deployments.csv',deployments);birth_ts={r['protocol']:ts(r['deployment_utc']) for r in deployments}
    liqtypes={'aave_v3':'LiquidationCall','compound_v3_usdc':'AbsorbDebt','morpho_blue':'Liquidate'}
    liqtypes={p:liqtypes[p] for p in protocols}
    hourly={}
    for p,name in liqtypes.items():
        for hour,count,txs,wallets in c.execute('SELECT stamp/3600,count(*),count(DISTINCT tx),count(DISTINCT account) FROM events WHERE protocol=? AND name=? GROUP BY stamp/3600',(p,name)):
            hourly[p,hour]=(count,txs,wallets)
    panel=[]
    for p in protocols:
        for h in range(ts('2023-01-27T00:00:00Z')//3600,ts('2026-10-01T00:00:00Z')//3600):
            available=(h+1)*3600>birth_ts[p];counts=hourly.get((p,h),(0,0,0))
            panel.append({'protocol':p,'hour_utc':utc(h*3600),'liquidation_events':counts[0] if available else '',
              'unique_transactions':counts[1] if available else '', 'unique_borrowers':counts[2] if available else '',
              'protocol_deployed':available,'measurement':liqtypes[p],'scope':'selected Ethereum contract only; predeployment is NA'})
    csv_write(OUT/'liquidations_hourly_full_period.csv',panel)
    # Protocol/year counts show the actual sample in each target calendar period.
    years=[]
    for p,year,name,n in c.execute("SELECT protocol,strftime('%Y',stamp,'unixepoch'),name,count(*) FROM events GROUP BY protocol,2,name"):
        if p not in protocols:continue
        years.append({'protocol':p,'year':int(year),'event_type':name,'records':n})
    csv_write(OUT/'event_counts_by_year.csv',years)
    # Decimals + symbol are raw unit metadata, distinct from a price history.
    tokens=set()
    for d, in c.execute("SELECT decoded FROM events WHERE protocol='aave_v3' AND name='LiquidationCall'"):
        r=json.loads(d);tokens.update([r['debtAsset'],r['collateralAsset']])
    for r in markets.values():tokens.update([r['loan_token'],r['collateral_token']])
    tokens.discard('0x'+'0'*40);tokens=sorted(tokens)
    calls=[]
    for token in tokens:calls.extend([call_request(token,'decimals()',[],end),call_request(token,'symbol()',[],end)])
    answers=rpc.many(calls,allow_errors=True);meta={}
    from .evm import decode_string
    for i,t in enumerate(tokens):
        a,b=answers[2*i:2*i+2]
        if isinstance(a,str) and isinstance(b,str):
            try:meta[t]={'token':t,'decimals':uint(words(a)[0]),'symbol':decode_string(b),'metadata_at_block':end}
            except Exception as e:errors.append({'token':t,'error':str(e)})
        else:errors.append({'token':t,'error':'Metadata call failed; no default decimals'})
    csv_write(OUT/'token_registry.csv',list(meta.values()))
    mapped={'0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2':'ETH/USD','0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48':'USDC/USD',
            '0xdac17f958d2ee523a2206206994597c13d831ec7':'USDT/USD','0x6b175474e89094c44da98b954eedeac495271d0f':'DAI/USD'}
    groups=defaultdict(Counter);valued=Counter();missing=Counter();n=0
    fields=['protocol','block','timestamp_utc','tx','logidx','borrower','liquidator','market','debt_token','collateral_token','reported_event_amount_raw','reported_event_amount',
            'reported_event_amount_market_usd','valuation_status','price_age_seconds','measurement','economic_meaning']
    with (OUT/'liquidations_model_table.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for p,b,stamp,tx,txidx,idx,mid,d in c.execute("SELECT protocol,block,stamp,tx,txidx,idx,market,decoded FROM events WHERE name IN ('LiquidationCall','AbsorbDebt','Liquidate') ORDER BY block,txidx,idx"):
            if p not in protocols:continue
            d=json.loads(d);n+=1
            if p=='aave_v3':borrower=d['user'];liquidator=d['liquidator'];debt=d['debtAsset'];coll=d['collateralAsset'];raw=d['debtToCover']
            elif p=='morpho_blue':
                m=markets.get(mid,{});borrower=d['borrower'];liquidator=d['caller'];debt=m.get('loan_token','');coll=m.get('collateral_token','');raw=d['repaidAssets']
            else:borrower=d['borrower'];liquidator=d['absorber'];debt='0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48';coll='';raw=d['basePaidOut']
            amount=D(raw)/10**meta[debt]['decimals'] if debt in meta else None;pricefeed=mapped.get(debt);value=None;age=''
            if amount is not None and pricefeed in feed:
                quote=price_before_event(feed[pricefeed],b,txidx,idx,stamp)
                if quote is not None:
                    age=stamp-quote['stamp'];threshold=7200 if pricefeed=='ETH/USD' else 90000
                    if age<=threshold:value=amount*D(quote['price_usd'])
            status='market_price_last_known' if value is not None else 'unpriced_or_stale; not zero'
            valued[p]+=value is not None;missing[p]+=value is None
            meaning='basePaidOut = debt absorbed plus possible positive base credit; not comparable to repaidAssets' if p=='compound_v3_usdc' else 'debt amount repaid in this liquidation event'
            writer.writerow(dict(zip(fields,[p,b,utc(stamp),tx,idx,borrower,liquidator,mid,debt,coll,str(raw),str(amount) if amount is not None else '',
                str(value) if value is not None else '',status,age,liqtypes[p],meaning])))
            for dimension,key in [('borrower',borrower),('liquidator',liquidator),('debt_token',debt),('collateral_token',coll)]:
                if key:groups[p,dimension][key]+=1
    concentration=[]
    for (p,dimension),counts in groups.items():
        total=sum(counts.values());shares=sorted(counts.values(),reverse=True)
        concentration.append({'protocol':p,'dimension':dimension,'categories':len(counts),'liquidation_events':total,
             'top1_event_share':shares[0]/total,'top10_event_share':sum(shares[:10])/total,'hhi_event_counts':sum((v/total)**2 for v in shares),
             'unit':'event counts, not total USD; do not interpret as USD concentration'})
    csv_write(OUT/'concentration_full_period_event_counts.csv',concentration)
    csv_write(OUT/'liquidation_valuation_coverage.csv',[{'protocol':p,'priced_events':valued[p],'unpriced_events':missing[p],
       'pricing':'Chainlink market price at/before event; WETH/USDC/USDT/DAI only; not claimed to equal Aave capped oracle'} for p in protocols])
    csv_write(OUT/'wallet_protocol_activity.csv',[{'account':a,'protocol':p,'events':n,'interpretation':'activity, not position or direct exposure'}
        for a,p,n in c.execute("SELECT account,protocol,count(*) FROM events WHERE account<>'' GROUP BY account,protocol") if p in protocols])
    save_json(RUN/'feature_errors.json',errors);c.close();print(f'FEATURES {n} liquidation-related debt events',flush=True)
if __name__=='__main__':main()
