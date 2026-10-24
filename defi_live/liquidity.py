"""Read-only, explicitly scoped Uniswap V3 quote collector.

Separate clock from prices/positions. Never substitutes live depth into historical
stress snapshots. Quoter is called via eth_call; no transaction is submitted.
"""
import math,time
from decimal import Decimal as D
from defi_data.pipeline import call,call_request,registry,metadata
from defi_data.evm import words,uint,addr
from defi_data.rpc import Rpc

FACTORY='0x1f98431c8ad98523631ae4a59f267346ea31f984'
QUOTER='0x61ffe014ba17989e743c5f6cb21bf9697530b21e'
POOLS=['0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640','0x4585fe77225b41b697c938b018e2ac67ac5a20c0']


def pool_quotes(rpc,pool,block,sizes=(1000,10000,100000,1000000)):
    tokens=[addr(call(rpc,pool,'token0()',[],block)[0]),addr(call(rpc,pool,'token1()',[],block)[0])]
    fee=uint(call(rpc,pool,'fee()',[],block)[0])
    registered=addr(call(rpc,FACTORY,'getPool(address,address,uint24)',[*tokens,fee],block)[0])
    if registered!=pool:raise ValueError('Uniswap pool registry mismatch')
    sqrt=uint(call(rpc,pool,'slot0()',[],block)[0]);meta=metadata(rpc,tokens,block)
    _,oracle,_=registry(rpc,block);base=D(uint(call(rpc,oracle,'BASE_CURRENCY_UNIT()',[],block)[0]))
    prices=rpc.many([call_request(oracle,'getAssetPrice(address)',[t],block) for t in tokens])
    spot=(D(sqrt)/D(2)**96)**2*D(10)**(meta[tokens[0]]['decimals']-meta[tokens[1]]['decimals'])
    rows=[];errors=[]
    for direction in (0,1):
        tin,tout=tokens[direction],tokens[1-direction];price=D(uint(words(prices[direction])[0]))/base
        if price<=0:raise ValueError('Missing input oracle valuation; no stablecoin peg assumed')
        for size in sizes:
            amount=int(D(size)/price*10**meta[tin]['decimals'])
            try:
                w=call(rpc,QUOTER,'quoteExactInputSingle((address,address,uint256,uint24,uint160))',[tin,tout,amount,fee,0],block)
                output=uint(w[0]);after=uint(w[1]);ratio=D(output)/10**meta[tout]['decimals']/(D(amount)/10**meta[tin]['decimals'])
                pre=spot if direction==0 else 1/spot;cost=1-ratio/pre;move=(D(after)/sqrt)**2-1
                if not 0<output or not all(math.isfinite(float(x)) for x in [ratio,cost,move]):raise ValueError('Invalid quote')
                rows.append({'pool':pool,'block':block,'token_in':tin,'token_out':tout,'symbol_in':meta[tin]['symbol'],'symbol_out':meta[tout]['symbol'],
                  'input_target_usd':size,'amount_in_raw':str(amount),'amount_out_raw':str(output),
                  'execution_price_out_per_in':str(ratio),'spot_out_per_in':str(pre),'cost_vs_spot_including_fee':str(cost),
                  'sqrt_price_after_x96':str(after),'price_move_token1_per_token0':str(move),'ticks_crossed':uint(w[2]),
                  'bounded_curve_usable':abs(move)<D('.8') and 0<=cost<1,
                  'source':'QuoterV2 eth_call at explicit block; no trade','fee_pips':fee})
            except Exception as exc:errors.append({'pool':pool,'token_in':tin,'size':size,'kind':getattr(exc,'kind',type(exc).__name__)})
    return rows,errors


class LiveLiquidity:
    def __init__(self,store):
        self.store=store;self.rpc=Rpc(store.folder/'liquidity_rpc',batch_size=20,multicall=True,use_cache=False,timeout=10,retry_attempts=1)
    def update(self):
        block=self.store.meta('cursor')
        if block is None:return
        h=self.store.header(block);rows=[];errors=[]
        for pool in POOLS:
            try:
                quotes,failed=pool_quotes(self.rpc,pool,block);rows+=quotes;errors+=failed
            except Exception as exc:errors.append({'pool':pool,'kind':getattr(exc,'kind',type(exc).__name__)})
        if not rows:raise ValueError('No valid liquidity quotes; previous product remains stale')
        check=self.rpc.one('eth_getBlockByNumber',[hex(block),False],cache=False)
        if check['hash']!=h['hash']:raise ValueError('Quotes invalidated by reorg')
        self.store.publish('liquidity',block,h['hash'],h['stamp'],{'quotes':rows,'errors':errors,'expected_quotes':len(POOLS)*8,
          'quote_coverage':len(rows)/(len(POOLS)*8),'pool_scope':POOLS,'historical_cascade_calibrated':False,
          'note':'Live quotes are block-specific. No routing, extrapolation or automatic reuse in historical stress.'})


def liquidity_loop(worker,stop,interval=900):
    while not stop.is_set():
        try:
            worker.store.set_meta('liquidity_job',{'state':'running','started_at':time.time()});worker.update()
            worker.store.set_meta('liquidity_job',{'state':'idle','finished_at':time.time()})
        except Exception as exc:worker.store.set_meta('liquidity_job',{'state':'error','kind':getattr(exc,'kind',type(exc).__name__),'at':time.time()})
        stop.wait(interval if worker.store.product('liquidity') else 30)
