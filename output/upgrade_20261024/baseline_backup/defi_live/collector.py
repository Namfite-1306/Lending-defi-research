import json,time,threading
from decimal import Decimal
from defi_data.rpc import Rpc,RpcError
from defi_data.pipeline import ROOT,CONTRACTS,call_request
from defi_data.evm import parse_events,decode_event,words,uint
from defi_data.recovery_prices import FEEDS

def header(raw):
    if not isinstance(raw,dict) or not raw.get('hash'):raise ValueError('Missing canonical block header')
    return {'number':int(raw['number'],16),'hash':raw['hash'],'parent':raw['parentHash'],'stamp':int(raw['timestamp'],16)}

class Collector:
    def __init__(self,store,confirmations=2,lookback=120,chunk=30,reorg_depth=64,start_block=None):
        self.store=store;self.confirmations=confirmations;self.lookback=lookback;self.chunk=chunk;self.reorg_depth=reorg_depth;self.start_block=start_block
        self.rpc=Rpc(store.folder/'rpc_cache',batch_size=30,use_cache=False,timeout=15,retry_attempts=2)
        self.specs={}
        for p,(a,source,names) in CONTRACTS.items():
            specs=parse_events((ROOT/'data/sources'/source).read_text(encoding='utf8'));self.specs[p]={specs[n]['topic']:(n,specs[n]) for n in names}
    def get_header(self,n):return header(self.rpc.one('eth_getBlockByNumber',[hex(n),False],cache=False))
    def canonicalize(self):
        cursor=self.store.meta('cursor');local=self.store.header(cursor);remote=self.get_header(cursor)
        if remote['hash']==local['hash']:return
        for number in range(cursor-1,max(-1,cursor-self.reorg_depth-1),-1):
            old=self.store.header(number)
            if old and self.get_header(number)['hash']==old['hash']:
                self.store.rollback(number);return
        raise RpcError('Reorg exceeds retained common-ancestor window; stop and rebuild live state in a new directory',kind='deep_reorg')
    def poll(self):
        if int(self.rpc.one('eth_chainId',[],cache=False),16)!=1:raise ValueError('Expected Ethereum mainnet')
        head=int(self.rpc.one('eth_blockNumber',[],cache=False),16);target=head-self.confirmations
        if target<1:raise ValueError('Invalid confirmed head')
        head_header=self.get_header(head)
        self.store.set_meta('head',{'number':head,'target':target,'stamp':head_header['stamp'],'observed_at':time.time()})
        identity={'chain_id':1,'confirmations':self.confirmations,'contracts':{p:v[0] for p,v in CONTRACTS.items()},'start_block_argument':self.start_block}
        if self.store.meta('cursor') is None:
            start=self.start_block if self.start_block is not None else max(1,target-self.lookback+1)
            if start>target:raise ValueError('Start block is newer than confirmed head')
            self.store.initialize(self.get_header(start-1),identity)
        elif self.store.meta('config')!=identity:raise ValueError('Live chain config changed; choose a new state directory')
        cursor=self.store.meta('cursor')
        if head<cursor:raise ValueError('RPC head behind local cursor; refusing to rewind to a lagging provider')
        self.canonicalize();cursor=self.store.meta('cursor');end=min(target,cursor+self.chunk)
        if end>cursor:
            heads=[header(r) for r in self.rpc.many([('eth_getBlockByNumber',[hex(n),False]) for n in range(cursor+1,end+1)])]
            bynum={h['number']:h for h in heads};events=[]
            for p,(address,_,_) in CONTRACTS.items():
                for log in self.rpc.logs(address,list(self.specs[p]),cursor+1,end):
                    n=int(log['blockNumber'],16);h=bynum[n]
                    if log['blockHash']!=h['hash']:raise ValueError('Log and header canonical hash disagree')
                    name,spec=self.specs[p][log['topics'][0]];decoded=decode_event(log,spec)
                    account=decoded.get('onBehalfOf',decoded.get('onBehalf',decoded.get('borrower',decoded.get('user',decoded.get('dst',decoded.get('src',''))))))
                    events.append({'tx':log['transactionHash'],'idx':int(log['logIndex'],16),'block':n,'hash':h['hash'],
                        'protocol':p,'name':name,'account':account,'token':decoded.get('reserve',decoded.get('asset','')),'stamp':h['stamp'],'decoded':decoded})
            # Recheck final header after fetching all contracts before committing.
            if self.get_header(end)['hash']!=heads[-1]['hash']:raise ValueError('Reorg occurred during log fetch; retry chunk')
            self.store.commit(heads,events)
        cursor=self.store.meta('cursor');self.store.set_meta('collector_status',{'state':'ok','last_success_at':time.time(),'cursor':cursor,'remaining_blocks':max(target-cursor,0)})
        return max(target-cursor,0)
    def prices(self):
        block=self.store.meta('cursor');h=self.store.header(block)
        calls=[]
        for proxy in FEEDS.values():calls.extend([call_request(proxy,'latestRoundData()',[],block),call_request(proxy,'decimals()',[],block)])
        answers=self.rpc.many(calls);prices=[]
        for i,(feed,proxy) in enumerate(FEEDS.items()):
            w=words(answers[2*i]);decimals=uint(words(answers[2*i+1])[0]);answer=uint(w[1]);updated=uint(w[3]);round_id=uint(w[0])
            if answer>=1<<255:answer-=1<<256
            if answer<=0 or not 0<updated<=h['stamp'] or uint(w[4])<round_id or decimals>36:raise ValueError('Invalid/future/incomplete Chainlink round')
            prices.append({'feed':feed,'price_usd':str(Decimal(answer)/10**decimals),'round_id':str(round_id),'updated_at':updated,
               'age_at_block_seconds':h['stamp']-updated,'heartbeat_limit_seconds':7200 if feed in ['ETH/USD','BTC/USD'] else 90000})
        self.store.publish('prices',block,h['hash'],h['stamp'],{'prices':prices,'unit':'USD; BTC/USD is not WBTC/USD'})

def collector_loop(collector,stop,interval):
    last_prices=0
    while not stop.is_set():
        delay=interval
        try:
            backlog=collector.poll()
            if time.time()-last_prices>=interval:
                try:collector.prices();last_prices=time.time();collector.store.set_meta('price_error',None)
                except Exception as e:collector.store.set_meta('price_error',{'kind':getattr(e,'kind',type(e).__name__),'at':time.time()})
            if backlog:delay=1
        except Exception as e:
            previous=collector.store.meta('collector_status',{})
            collector.store.set_meta('collector_status',dict(previous,state='error',error_kind=getattr(e,'kind',type(e).__name__),error_at=time.time()))
        stop.wait(delay)
