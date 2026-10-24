"""Historical Uniswap V3 depth and exact contract quotes, with explicit coverage bounds."""
from decimal import Decimal as D
import json,argparse
from collections import defaultdict
from .recovery import RUN,OUT,OLD
from .expansion import read_csv,signed
from .pipeline import ROOT,call,call_request,registry,metadata,csv_write,save_json
from .evm import words,uint,addr
from .rpc import Rpc

FACTORY='0x1f98431c8ad98523631ae4a59f267346ea31f984'
QUOTER='0x61ffe014ba17989e743c5f6cb21bf9697530b21e'

def main():
    OUT.mkdir(parents=True,exist_ok=True);rpc=Rpc(ROOT/'data/rpc_cache',batch_size=25,multicall=True)
    pools=read_csv(OLD/'processed/dex_liquidity_sample.csv');ticks=[];quotes=[];checks=[];errors=[]
    for p in pools:
        if p['type']!='v3' or p['factory']!=FACTORY:continue
        pool=p['pool'];b=int(p['block_number'])
        try:
            fee=uint(call(rpc,pool,'fee()',[],b)[0]);spacing=signed(call(rpc,pool,'tickSpacing()',[],b)[0])
            registered=addr(call(rpc,FACTORY,'getPool(address,address,uint24)',[p['token0'],p['token1'],fee],b)[0])
            if registered!=pool:raise ValueError('Factory pool registry mismatch')
            state=call(rpc,pool,'slot0()',[],b);current=signed(state[1]);sqrt=uint(state[0])
            low=max(-887272,current-6000);high=min(887272,current+6000)
            word_lo=(low//spacing)>>8;word_hi=(high//spacing)>>8
            bitmaps=rpc.many([call_request(pool,'tickBitmap(int16)',[i],b) for i in range(word_lo,word_hi+1)])
            initialized=[]
            for wi,result in zip(range(word_lo,word_hi+1),bitmaps):
                bitmap=uint(words(result)[0])
                for bit in range(256):
                    tick=(wi*256+bit)*spacing
                    if bitmap>>bit&1 and -887272<=tick<=887272:initialized.append(tick)
            states=rpc.many([call_request(pool,'ticks(int24)',[t],b) for t in initialized])
            for tick,result in zip(initialized,states):
                w=words(result);gross=uint(w[0]);net=signed(w[1]);valid=bool(uint(w[7])) and gross>0 and abs(net)<=gross
                if not valid:raise ValueError('Tick bitmap/state invariant failed')
                ticks.append({'pool':pool,'block':b,'tick':tick,'liquidity_gross':str(gross),'liquidity_net':str(net),
                              'initialized':True,'spacing':spacing,'collection_low':low,'collection_high':high})
            tokens=[p['token0'],p['token1']];meta=metadata(rpc,tokens,b);_,oracle,_=registry(rpc,b)
            prices=rpc.many([call_request(oracle,'getAssetPrice(address)',[t],b) for t in tokens],allow_errors=True)
            base=uint(call(rpc,oracle,'BASE_CURRENCY_UNIT()',[],b)[0]);spot=(D(sqrt)/D(2)**96)**2*D(10)**(meta[tokens[0]]['decimals']-meta[tokens[1]]['decimals'])
            for direction in (0,1):
                tin=tokens[direction];tout=tokens[1-direction];price=prices[direction]
                if not isinstance(price,str) or not uint(words(price)[0]):
                    errors.append({'pool':pool,'stage':'input USD sizing','token':tin,'error':'No oracle price; no assumed stablecoin peg'});continue
                usd=D(uint(words(price)[0]))/base
                for size in (1000,10000,100000,1000000,10000000):
                    amount=int(D(size)/usd*10**meta[tin]['decimals'])
                    try:
                        w=call(rpc,QUOTER,'quoteExactInputSingle((address,address,uint256,uint24,uint160))',[tin,tout,amount,fee,0],b)
                        output=uint(w[0]);after=uint(w[1]);ratio=D(output)/10**meta[tout]['decimals']/(D(amount)/10**meta[tin]['decimals'])
                        pre=spot if direction==0 else 1/spot;move=(D(after)/sqrt)**2-1
                        quotes.append({'pool':pool,'block':b,'token_in':tin,'token_out':tout,'input_target_usd':size,'amount_in_raw':str(amount),
                          'amount_out_raw':str(output),'execution_price_out_per_in':str(ratio),'spot_out_per_in':str(pre),
                          'cost_vs_spot_including_fee':str(1-ratio/pre),'sqrt_price_after_x96':str(after),'price_move_token1_per_token0':str(move),
                          'ticks_crossed':uint(w[2]),'quote_gas_estimate':uint(w[3]),
                          'bounded_curve_usable':abs(move)<D('.8') and output>0,'source':'historical QuoterV2 eth_call; exact pool computation',
                          'timing':'previous block end; not pre-transaction state','scope':'verified Uniswap V3 pools only'})
                    except Exception as e:errors.append({'pool':pool,'stage':'quote','direction':direction,'size':size,'error':str(e)[:300]})
            checks.append({'pool':pool,'block':b,'factory_registry_match':True,'tick_states_valid':True,'tick_count':len(initialized),
                           'word_count':word_hi-word_lo+1,'full_tick_range':False,'scope':'bounded +/-6000 ticks; exact quotes use node full state'})
            print(f'D pool {len(checks)}: {len(initialized)} ticks; {len(quotes)} quotes total',flush=True)
        except Exception as e:errors.append({'pool':pool,'stage':'pool','error':str(e)[:350]})
        csv_write(OUT/'v3_initialized_ticks.csv',ticks);csv_write(OUT/'v3_exact_impact_quotes.csv',quotes)
        csv_write(OUT/'v3_pool_validation.csv',checks);save_json(RUN/'dex_recovery_errors.json',errors)
def replay():
    rpc=Rpc(ROOT/'data/rpc_cache',urls=['https://eth.drpc.org','https://eth-mainnet.public.blastapi.io'],batch_size=20,multicall=True)
    from .recovery_trace_funding import traced,flatten
    verified={r['pool'] for r in read_csv(OUT/'v3_pool_validation.csv')};results=[]
    for case in read_csv(OLD/'processed/dex_swaps_sample.csv'):
        if case['pool'] not in verified or case['pool_type']!='v3':continue
        pool=case['pool'];b=int(case['block_number']);tx=case['tx_hash'];idx=int(case['log_index'])
        try:
            receipt=rpc.one('eth_getTransactionReceipt',[tx]);log=next(l for l in receipt['logs'] if int(l['logIndex'],16)==idx)
            previous=rpc.one('eth_getLogs',[{'address':pool,'fromBlock':hex(b),'toBlock':hex(b)}],cache=False)
            txi=int(receipt['transactionIndex'],16)
            earlier=any((int(l['transactionIndex'],16),int(l['logIndex'],16))<(txi,idx) for l in previous)
            if earlier:
                results.append({'tx':tx,'pool':pool,'block':b,'logidx':idx,'eligible':False,'status':'earlier pool activity in block; needs intra-block replay'});continue
            w=words(log['data']);a0,a1=signed(w[0]),signed(w[1]);direction=0 if a0>0 else 1
            tokens=[addr(call(rpc,pool,'token0()',[],b-1)[0]),addr(call(rpc,pool,'token1()',[],b-1)[0])]
            fee=uint(call(rpc,pool,'fee()',[],b-1)[0]);amount=a0 if direction==0 else a1;actual=-a1 if direction==0 else -a0
            swaps=[n for n in flatten(traced(tx,'callTracer')) if n.get('to','').lower()==pool and n.get('input','').startswith('0x128acb08')]
            if len(swaps)!=1:raise ValueError('Ambiguous swap call; needs call/log association')
            args=words('0x'+swaps[0]['input'][10:10+4*64]);specified=signed(args[2]);limit=uint(args[3])
            exact_input=specified>0
            signature='quoteExactInputSingle((address,address,uint256,uint24,uint160))' if exact_input else 'quoteExactOutputSingle((address,address,uint256,uint24,uint160))'
            quote=call(rpc,QUOTER,signature,[tokens[direction],tokens[1-direction],abs(specified),fee,limit],b-1)
            predicted=uint(quote[0]);expected=actual if exact_input else amount
            price_match=uint(quote[1])==uint(w[2]);exact=predicted==expected and price_match
            results.append({'tx':tx,'pool':pool,'block':b,'logidx':idx,'eligible':True,'actual_out_raw':str(actual),
                'predicted_quote_raw':str(predicted),'expected_quote_raw':str(expected),'quote_kind':'exact_input_output' if exact_input else 'exact_output_input','sqrt_price_limit_x96':str(limit),'absolute_error_raw':str(abs(predicted-expected)),'sqrt_price_exact_match':price_match,
                'exact_replay_match':exact,'status':'matched' if exact else 'mismatch; investigate limit/rounding/token behavior'})
        except Exception as e:results.append({'tx':tx,'pool':pool,'block':b,'logidx':idx,'eligible':False,'status':str(e)[:350]})
        csv_write(OUT/'v3_swap_replay_validation.csv',results)
    csv_write(OUT/'v3_swap_replay_validation.csv',results)
    print(f'D swap replay: {len(results)} cases, {sum(r.get("exact_replay_match",False) for r in results)} exact',flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--replay',action='store_true');a=p.parse_args()
    if a.replay:replay()
    else:main()
