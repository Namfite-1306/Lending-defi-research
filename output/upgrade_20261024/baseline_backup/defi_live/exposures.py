"""Current same-block exposures for the monitored cohort; never a full market claim."""
from decimal import Decimal as D
from defi_data.pipeline import CONTRACTS,call,call_request,metadata
from defi_data.evm import addr,uint,words
from defi_data.recovery import simulated_accrual,to_assets_up

def exposures(rpc,store,wallets,block,positions,oracle):
    rows=[];errors=[];comet=CONTRACTS['compound_v3_usdc'][0];morpho=CONTRACTS['morpho_blue'][0]
    for r in positions:
        for kind,key in [('collateral','collateral_usd'),('debt','debt_usd')]:
            if D(r[key])>0:rows.append({'protocol':'aave_v3','wallet':r['account'],'market':CONTRACTS['aave_v3'][0],'asset':r['token'],'kind':kind,'value_usd':r[key]})
    try:
        base=addr(call(rpc,comet,'baseToken()',[],block)[0]);base_scale=uint(call(rpc,comet,'baseScale()',[],block)[0]);feed=addr(call(rpc,comet,'baseTokenPriceFeed()',[],block)[0])
        base_price=D(uint(call(rpc,comet,'getPrice(address)',[feed],block)[0]))/10**8
        answers=rpc.many([call_request(comet,'borrowBalanceOf(address)',[a],block) for a in wallets])
        borrowers=[(a,uint(words(r)[0])) for a,r in zip(wallets,answers) if uint(words(r)[0])>0]
        for a,debt in borrowers:rows.append({'protocol':'compound_v3_usdc','wallet':a,'market':comet,'asset':base,'kind':'debt','value_usd':str(D(debt)/base_scale*base_price)})
        if borrowers:
            count=uint(call(rpc,comet,'numAssets()',[],block)[0])
            if count>64:raise ValueError('Unexpected Comet asset count')
            assets=rpc.many([call_request(comet,'getAssetInfo(uint8)',[i],block) for i in range(count)])
            for data in assets:
                w=words(data);asset=addr(w[1]);asset_feed=addr(w[2]);scale=uint(w[3]);price=D(uint(call(rpc,comet,'getPrice(address)',[asset_feed],block)[0]))/10**8
                balances=rpc.many([call_request(comet,'collateralBalanceOf(address,address)',[a,asset],block) for a,_ in borrowers])
                for (a,_),r in zip(borrowers,balances):
                    amount=uint(words(r)[0])
                    if amount:rows.append({'protocol':'compound_v3_usdc','wallet':a,'market':comet,'asset':asset,'kind':'collateral','value_usd':str(D(amount)/scale*price)})
    except Exception as e:errors.append({'protocol':'compound_v3_usdc','stage':'current_exposure','error_kind':getattr(e,'kind',type(e).__name__)})
    # Market membership comes only from observed Morpho activity for monitored wallets.
    with store.db() as c:
        mids=set()
        placeholders=','.join('?' for _ in wallets)
        for row in c.execute(f"SELECT account,decoded FROM events WHERE protocol='morpho_blue' AND block<=? AND account IN ({placeholders})",[block]+wallets):
            if row['account'] in wallets:
                import json
                market=json.loads(row['decoded']).get('id')
                if market:mids.add(market)
    capped=len(mids)>20;mids=sorted(mids)[:20]
    for mid in mids:
        try:
            params=call(rpc,morpho,'idToMarketParams(bytes32)',[mid],block)
            if len(params)!=5:raise ValueError('Unknown Morpho parameter ABI')
            values=[addr(v) for v in params[:4]]+[uint(params[4])];loan,collateral=values[:2]
            state=simulated_accrual(rpc,morpho,values,mid,block)
            meta=metadata(rpc,[loan],block);unit=10**meta[loan]['decimals'];price=D(uint(call(rpc,oracle,'getAssetPrice(address)',[loan],block)[0]))/10**8
            if price<=0:raise ValueError('No validated loan-token USD oracle')
            collateral_price=uint(call(rpc,values[2],'price()',[],block)[0])
            answers=rpc.many([call_request(morpho,'position(bytes32,address)',[mid,a],block) for a in wallets])
            for a,result in zip(wallets,answers):
                w=words(result);debt=to_assets_up(uint(w[1]),state[2],state[3]);coll=uint(w[2])
                for kind,asset,amount in [('debt',loan,debt),('collateral',collateral,coll*collateral_price//10**36)]:
                    if amount:rows.append({'protocol':'morpho_blue','wallet':a,'market':mid,'asset':asset,'kind':kind,'value_usd':str(D(amount)/unit*price)})
        except Exception as e:errors.append({'protocol':'morpho_blue','market':mid,'error_kind':getattr(e,'kind',type(e).__name__)})
    return {'edges':rows,'errors':errors,'morpho_markets_checked':len(mids),'morpho_market_list_capped':capped,
       'scope':'current monitored wallets; Morpho membership only from observed live activity, not all markets',
       'causal_contagion_estimated':False}
