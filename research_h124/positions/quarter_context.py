"""Observed quarterly HF stock and reserve utilization; never fake 5m values."""
from decimal import Decimal as D
from defi_data.rpc import Rpc
from defi_data.pipeline import call_request
from defi_data.evm import words,uint,addr
from .v2_common import *

def basis_at_quarter(rpc,item,metadata):
    from defi_live.liquidity import FACTORY
    from defi_data.recovery_prices import FEEDS
    weth=next(r['token'] for r in metadata if r['symbol']=='WETH');block=item['block'];rows=[]
    for symbol in ['wstETH','WBTC']:
        row={'quarter':item['quarter'],'block':block,'symbol':symbol,'frequency':'quarter_end_only','selection':'largest active liquidity among four Uniswap V3 fee tiers, same pair'}
        try:
            token=next(r['token'] for r in metadata if r['symbol']==symbol);decimals=int(next(r['decimals'] for r in metadata if r['token']==token))
            values=rpc.many([call_request(FACTORY,'getPool(address,address,uint24)',[token,weth,fee],block) for fee in [100,500,3000,10000]])
            pools=[addr(words(v)[0]) for v in values if int(words(v)[0],16)>0]
            if not pools:raise ValueError('No direct pool')
            liquidity=rpc.many([call_request(p,'liquidity()',[],block) for p in pools]);selected=max(zip(pools,liquidity),key=lambda p:uint(words(p[1])[0]))
            if uint(words(selected[1])[0])<=0:raise ValueError('No active pool liquidity')
            pool=selected[0];raw,token0=rpc.many([call_request(pool,'slot0()',[],block),call_request(pool,'token0()',[],block)])
            zero=addr(words(token0)[0]);sqrt=D(uint(words(raw)[0]))/2**96
            ratio=sqrt*sqrt*D(10)**(decimals-18 if zero==token else 18-decimals)
            weth_per_token=ratio if zero==token else 1/ratio
            if symbol=='wstETH':
                conversion=uint(words(rpc.one(*call_request(token,'stEthPerToken()',[],block)))[0]);reference=D(conversion)/10**18
                basis=weth_per_token/reference-1;meaning='DEX implied stETH/ETH minus 1; adjusts wstETH redemption ratio'
            else:
                eth,btc=rpc.many([call_request(FEEDS[f],'latestRoundData()',[],block) for f in ['ETH/USD','BTC/USD']]);ew=words(eth);bw=words(btc)
                if any(item['stamp']-uint(w[3])>7200 or uint(w[3])>item['stamp'] for w in [ew,bw]):raise ValueError('Stale/future reference feed')
                reference=D(uint(bw[1]))/uint(ew[1]);basis=weth_per_token/reference-1;meaning='WBTC/WETH DEX spot versus Chainlink BTC/ETH cross'
            row.update(status='observed_quarter_spot',pool=pool,weth_per_token=str(weth_per_token),reference_weth_per_token=str(reference),basis=str(basis),meaning=meaning)
        except Exception as exc:row.update(status='not_observed',kind=getattr(exc,'kind',type(exc).__name__))
        rows.append(row)
    return rows

def run():
    hf_rows=[];reserve_rows=[];basis_rows=[];errors=[];basket_rows=[];previous=None
    rpc=Rpc(DATA/'quarter_context_rpc',batch_size=50,multicall=True,timeout=12,retry_attempts=1)
    for item in load(H1_DATA/'h1/quarter_plan.json',[]):
        folder=H1_DATA/'h1'/item['quarter'];scope=load(folder/'scope.json',{})
        if not scope.get('full_snapshot_complete'):continue
        freeze=load(folder/'freeze_manifest.json',{})
        if not freeze or any(digest(folder/name)!=value for name,value in freeze['files'].items()):raise ValueError('Quarter context freeze mismatch')
        metadata=read(folder/'reserve_metadata.csv');positions=read(folder/'positions.csv')
        from defi_models.core import DEFAULTS
        weights={};prices={r['token']:D(r['price_usd']) for r in positions}
        for r in positions:
            if r['symbol'] not in DEFAULTS['eth_symbols']+DEFAULTS['btc_symbols']:weights[r['token']]=weights.get(r['token'],D(0))+D(r['collateral_usd'])
        if previous:
            prior_weights,prior_prices=previous;total_weight=sum(prior_weights.values());covered=sum(w for token,w in prior_weights.items() if token in prices and prior_prices.get(token,D(0))>0)
            ratio=sum(w*prices[token]/prior_prices[token] for token,w in prior_weights.items() if token in prices and prior_prices.get(token,D(0))>0)/total_weight if total_weight else None
            coverage=covered/total_weight if total_weight else D(0)
            basket_rows.append({'quarter':item['quarter'],'block':item['block'],'prior_quarter_weight_coverage':str(coverage),
              'oracle_basket_price_ratio':str(ratio) if coverage>=D('.99') and ratio is not None else None,'frequency':'quarter_to_quarter_only',
              'definition':'Aave oracle price ratio with prior-quarter collateral USD weights; excludes ETH/BTC factor families, includes stablecoins; not an independent exchange index or 5-minute interpolation'})
        previous=weights,prices
        basis_cache=DATA/'quarter_context'/item['quarter']/'basis.csv'
        if basis_cache.exists():basis_rows+=read(basis_cache)
        else:
            basis=basis_at_quarter(rpc,item,metadata);write(basis_cache,basis);basis_rows+=basis
        checks=read(folder/'validation.csv');total=sum(D(r['debt_reported_usd']) for r in checks)
        hf_rows.append({'quarter':item['quarter'],'block':item['block'],'available_block_timestamp':item['stamp'],'active_wallets':len(checks),
          'risk_debt_usd':str(total),'debt_share_hf_lt1':str(sum(D(r['debt_reported_usd']) for r in checks if D(r['hf_reported'])<1)/total),
          'debt_share_hf_1_to_1_1':str(sum(D(r['debt_reported_usd']) for r in checks if 1<=D(r['hf_reported'])<D('1.1'))/total),
          'frequency':'quarter_end_only','not_current_5min_HF':True,'snapshot_freeze_sha256':digest(folder/'freeze_manifest.json')})
        cached=DATA/'quarter_context'/item['quarter']/'reserves.csv'
        if cached.exists():reserve_rows+=read(cached);continue
        local=[]
        for meta in read(folder/'reserve_metadata.csv'):
            if meta['symbol'] not in ['WETH','USDC']:continue
            token=meta['token'];block=item['block'];row={'quarter':item['quarter'],'block':block,'token':token,'symbol':meta['symbol'],'frequency':'quarter_end_only'}
            try:
                addresses,data=rpc.many([call_request(scope['provider'],'getReserveTokensAddresses(address)',[token],block),call_request(scope['provider'],'getReserveData(address)',[token],block)])
                w=words(data)
                if len(w)!=12:raise ValueError('Unknown provider reserve data ABI')
                virtual=scope['pool_revision']>=8 or bool((int(meta['configuration_word'])>>252)&1)
                request=call_request(scope['pool'],'getVirtualUnderlyingBalance(address)',[token],block) if virtual else call_request(token,'balanceOf(address)',[addr(words(addresses)[0])],block)
                available=uint(words(rpc.one(*request))[0]);debt=uint(w[3])+uint(w[4]);denominator=available+debt
                row.update(status='observed',available_native_raw=str(available),total_debt_native_raw=str(debt),
                  borrow_usage_ratio=str(D(debt)/denominator) if denominator else None,variable_borrow_APR=str(D(uint(w[6]))/10**27),
                  liquidity_basis='virtual underlying balance' if virtual else 'underlying balance of aToken',configuration_word=meta['configuration_word'])
            except Exception as exc:row.update(status='source_error',kind=getattr(exc,'kind',type(exc).__name__));errors.append(row)
            local.append(row)
        if local and all(r['status']=='observed' for r in local):write(cached,local)
        reserve_rows+=local
    write(OUT/'h4_quarterly_risk_context.csv',hf_rows);write(OUT/'h4_quarterly_reserve_context.csv',reserve_rows)
    write(OUT/'h4_quarterly_basis.csv',basis_rows);write(OUT/'h4_quarterly_basket.csv',basket_rows)
    result={'updated_utc':now(),'quarter_HF_rows':len(hf_rows),'reserve_rows':len(reserve_rows),'basis_rows':len(basis_rows),'basket_rows':len(basket_rows),'errors':len(errors),'status':'quarterly_observed_context_only',
      'limitations':['Not interpolated/forward-labelled as current 5-minute HF or utilization','Not included in the high-frequency H4 primary fit','High-frequency HF requires historical balance reconstruction between cutoffs']}
    save(OUT/'h4_quarterly_context.json',result);return result
if __name__=='__main__':print(run())
