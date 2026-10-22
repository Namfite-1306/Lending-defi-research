"""Historical Chainlink market controls, proxy phases and backward-only hourly alignment."""
import json,time
from decimal import Decimal as D
from .recovery import RUN,OUT,OLD,http
from .pipeline import ROOT,call,call_request,csv_write,save_json,ts,utc
from .evm import topic,words,uint,addr,decode_string
from .rpc import Rpc
from .price_history import PRICE_SCHEMA_VERSION,BLOCK_END,build_price_index,price_at_time
FEEDS={'ETH/USD':'0x5f4ec3df9cbd43714fe2740f5e3616155c5b8419','BTC/USD':'0xf4030086522a5beea4988f8ca5b36dbc97bee88c',
       'USDC/USD':'0x8fffffd4afb6115b954bd326cbe7b4ba576818f6','USDT/USD':'0x3e7d1eab13ad0104d2750b8863b489d65364e32d',
       'DAI/USD':'0xaed0c38402a5d19df6e4c03f4e2dced6e29c1ee9'}
def main():
    OUT.mkdir(parents=True,exist_ok=True);rpc=Rpc(ROOT/'data/rpc_cache',batch_size=20,multicall=True)
    bounds=json.loads((OLD/'block_range.json').read_text(encoding='utf8'));start,end=bounds['start_block'],bounds['end_block']
    answer=topic('AnswerUpdated(int256,uint256,uint256)');confirm=topic('AggregatorConfirmed(address,address)')
    def logs(address,topic0,lo,hi):
        params=[{'address':address,'topics':[topic0],'fromBlock':hex(lo),'toBlock':hex(hi)}]
        path=rpc._path('eth_getLogs',params)
        if path.exists():return json.loads(path.read_text(encoding='utf8'))
        for attempt in range(5):
            try:
                data=http('https://rpc.mevblocker.io','eth_getLogs',params)
                if len(data)>=9500 and hi>lo:
                    mid=(lo+hi)//2;data=logs(address,topic0,lo,mid)+logs(address,topic0,mid+1,hi)
                path.write_text(json.dumps(data),encoding='utf8');return data
            except Exception as e:
                if hi-lo>10000 and any(x in str(e).lower() for x in ('range','size','limit','temporarily unavailable','timed out')):
                    mid=(lo+hi)//2;return logs(address,topic0,lo,mid)+logs(address,topic0,mid+1,hi)
                if attempt==4:raise
                time.sleep(2**attempt)
    updates=[];phases=[];hourly=[];metadata=[];block_times={}
    for name,proxy in FEEDS.items():
        desc=decode_string(rpc.one(*call_request(proxy,'description()',[],start)))
        decimals=uint(call(rpc,proxy,'decimals()',[],start)[0])
        if desc.replace(' ','')!=name:raise ValueError(f'Unexpected feed description {desc}')
        initial=addr(call(rpc,proxy,'aggregator()',[],start)[0])
        transitions=sorted(logs(proxy,confirm,start,end),key=lambda l:(int(l['blockNumber'],16),int(l['logIndex'],16)))
        first_phase=uint(call(rpc,proxy,'phaseId()',[],start)[0]);last_phase=uint(call(rpc,proxy,'phaseId()',[],end)[0])
        # Derive transitions from monotone historical state as well as event logs.
        # Some proxy generations use a different confirmation event ABI.
        boundaries=[start]
        for phase in range(first_phase+1,last_phase+1):
            left,right=boundaries[-1],end
            while left<right:
                mid=(left+right)//2
                if uint(call(rpc,proxy,'phaseId()',[],mid)[0])<phase:left=mid+1
                else:right=mid
            boundaries.append(left)
        aggregators=rpc.many([call_request(proxy,'phaseAggregators(uint16)',[p],end) for p in range(first_phase,last_phase+1)])
        segments=[(addr(words(agg)[0]),b,boundaries[i+1]-1 if i+1<len(boundaries) else end)
                  for i,(agg,b) in enumerate(zip(aggregators,boundaries))]
        round0=call(rpc,proxy,'latestRoundData()',[],start-1)
        prior={'feed':name,'proxy':proxy,'aggregator':'proxy_seed','block':start-1,'stamp':uint(round0[3]),
               'available_stamp':int(rpc.block(start-1)['timestamp'],16),'transaction_index':BLOCK_END,'log_index':BLOCK_END,
               'schema_version':PRICE_SCHEMA_VERSION,
               'price_usd':str(D(uint(round0[1]))/10**decimals),'round_id':str(uint(round0[0])),'source':'latestRoundData before target start'}
        feed_updates=[prior]
        for agg,a,b in segments:
            if b<a:continue
            if a>start:
                seed=call(rpc,proxy,'latestRoundData()',[],a);available=int(rpc.block(a)['timestamp'],16)
                feed_updates.append({'feed':name,'proxy':proxy,'aggregator':agg,'block':a,'stamp':uint(seed[3]),
                    'available_stamp':available,'transaction_index':BLOCK_END,'log_index':BLOCK_END,'schema_version':PRICE_SCHEMA_VERSION,
                    'price_usd':str(D(uint(seed[1]))/10**decimals),'round_id':str(uint(seed[0])),
                    'source':'new phase initial quote; available from activation block, not earlier'})
            raw=logs(agg,answer,a,b);phases.append({'feed':name,'proxy':proxy,'aggregator':agg,'from_block':a,'to_block':b,'events':len(raw)})
            missing=sorted({int(l['blockNumber'],16) for l in raw if not l.get('blockTimestamp')}-block_times.keys())
            headers=rpc.many([('eth_getBlockByNumber',[hex(bn),False]) for bn in missing])
            for bn,header in zip(missing,headers):block_times[bn]=int(header['timestamp'],16)
            for l in raw:
                value=uint(l['topics'][1]);stamp=uint(words(l['data'])[0])
                if value>=1<<255:value-=1<<256
                if value<=0:raise ValueError('Nonpositive Chainlink price')
                feed_updates.append({'feed':name,'proxy':proxy,'aggregator':agg,'block':int(l['blockNumber'],16),'stamp':stamp,
                    'available_stamp':int(l['blockTimestamp'],16) if l.get('blockTimestamp') else block_times[int(l['blockNumber'],16)],
                    'transaction_index':int(l['transactionIndex'],16),'log_index':int(l['logIndex'],16),'schema_version':PRICE_SCHEMA_VERSION,
                    'price_usd':str(D(value)/10**decimals),'round_id':str(uint(l['topics'][2])),'source':'active phase AnswerUpdated'})
        feed_updates.sort(key=lambda r:(r['block'],r['transaction_index'],r['log_index']))
        index=build_price_index(feed_updates)[name];updates+=feed_updates
        for stamp in range(ts('2023-01-27T00:00:00Z'),ts('2026-10-01T00:00:00Z'),3600):
            r=price_at_time(index,stamp)
            if r is None:hourly.append({'feed':name,'timestamp_utc':utc(stamp),'price_usd':'','source_update_utc':'','source_available_utc':'','age_seconds':'','stale':True});continue
            age=stamp-r['stamp']
            hourly.append({'feed':name,'timestamp_utc':utc(stamp),'price_usd':r['price_usd'],'source_update_utc':utc(r['stamp']),
                            'source_available_utc':utc(r['available_stamp']),
                            'age_seconds':age,'stale':age>(7200 if name in ('ETH/USD','BTC/USD') else 90000),
                            'alignment':'last observation at or BEFORE hour; no future interpolation'})
        metadata.append({'feed':name,'proxy':proxy,'description':desc,'decimals':decimals,'events':len(feed_updates),'phase_segments':len(segments),
                         'scope':'market control; BTC/USD is not a claim that WBTC/BTC basis is zero'})
        print(f'D price feed {name}: {len(feed_updates)} observations',flush=True)
        csv_write(OUT/'chainlink_price_updates.csv',updates);csv_write(OUT/'market_prices_hourly_full_period.csv',hourly)
        csv_write(OUT/'chainlink_phase_segments.csv',phases);save_json(RUN/'chainlink_feed_metadata.json',metadata)
if __name__=='__main__':main()
