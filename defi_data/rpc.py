import hashlib
import json
import os
import time
import urllib.request
import urllib.error
import uuid
from pathlib import Path

def error_kind(error):
    text=str(error).lower()
    if any(x in text for x in ('4444','pruned','missing trie','historical state','archive requests','history unavailable')):return 'history_unavailable'
    if any(x in text for x in ('429','rate limit','compute units','too many requests')):return 'rate_limit'
    if any(x in text for x in ('401','403','unauthorized','personal token','api key','access denied')):return 'authorization'
    if any(x in text for x in ('block range','blocks range','range limit','maximum block','too many results','response size','query returned more','range too large')):return 'range_limit'
    if any(x in text for x in ('method not found','method_not','-32601','not support batch')):return 'unsupported_method'
    if any(x in text for x in ('network','timeout','timed out','temporarily unavailable','502','503','504')):return 'network'
    return 'rpc_error'

class RpcError(RuntimeError):
    def __init__(self,message,kind=None):
        super().__init__(message);self.kind=kind or error_kind(message)

class Rpc:
    def __init__(self, cache, urls=None, batch_size=20, multicall=False, cache_individual=True,timeout=35,retry_attempts=3,use_cache=True):
        self.urls=[u.strip() for u in (urls or os.getenv('ETH_RPC_URLS','https://rpc.mevblocker.io,https://eth.drpc.org,https://eth-mainnet.public.blastapi.io').split(',')) if u.strip()]
        if not self.urls:raise RpcError('No RPC configured. Set ETH_RPC_URLS.',kind='configuration')
        # Isolate old caches that may contain misleading empty historical results.
        self.cache=Path(cache)/'transport_v2'; self.cache.mkdir(parents=True,exist_ok=True)
        self.batch_size=batch_size; self.requests=0; self.hits=0
        self.multicall=multicall
        self.cache_individual=cache_individual
        self.timeout=timeout;self.retry_attempts=retry_attempts
        self.use_cache=use_cache

    def _path(self,method,params):
        key=json.dumps([method,params],sort_keys=True,separators=(',',':')).encode()
        return self.cache/(hashlib.sha256(key).hexdigest()+'.json')

    def _post(self,payload):
        # Endpoints/keys are never written to manifests or error messages.
        last=''; semantic_error=None;range_error=None
        for attempt in range(self.retry_attempts):
            transient=False
            for url in self.urls:
                try:
                    req=urllib.request.Request(url,json.dumps(payload).encode(),
                        {'Content-Type':'application/json','User-Agent':'DeFiResearch/1.0'})
                    with urllib.request.urlopen(req,timeout=self.timeout) as response:
                        result=json.load(response)
                    self.requests+=1
                    if self.requests % 25 == 0:
                        print(f'RPC progress: {self.requests} HTTP requests, {self.hits} cache hits',flush=True)
                    time.sleep(.08)
                    if not isinstance(result,(dict,list)) or (isinstance(result,list) and not isinstance(payload,list)):
                        semantic_error={'error':{'message':'Malformed RPC response'}};continue
                    if isinstance(result,dict) and 'error' in result:
                        semantic_error=result
                        if error_kind(result['error'])=='range_limit':range_error=result
                        msg=str(result['error']).lower()
                        transient=transient or any(x in msg for x in ('429','rate limit','compute units','too many requests'))
                        continue
                    if isinstance(result,dict) and result.get('result') is None:
                        semantic_error={'error':{'message':'Missing RPC result'}};continue
                    return result
                except urllib.error.HTTPError as exc:
                    # A JSON-RPC error can arrive with HTTP 400/403/429. Preserve it;
                    # hiding it caused oversized queries to fall through to pruned providers.
                    try:
                        error=json.loads(exc.read())
                        if isinstance(error,dict) and 'error' in error:
                            semantic_error=error
                            if error_kind(error['error'])=='range_limit':range_error=error
                            transient=transient or exc.code==429
                    except (ValueError,UnicodeError):pass
                    last=f'HTTP {exc.code}'
                    if exc.code in (401,403,429):
                        semantic_error=semantic_error or {'error':{'code':exc.code,'message':last}}
                        transient=transient or exc.code==429
                except Exception as exc: last=type(exc).__name__
            if semantic_error is not None:
                err=semantic_error.get('error',{})
                message=str(err.get('message','')).lower()
                if not transient and err.get('code') not in (429,) and not any(x in message for x in ('rate limit','compute units','too many requests')):
                    return range_error or semantic_error
            if attempt+1<self.retry_attempts:time.sleep(.5*(2**attempt))
        if semantic_error is not None:return range_error or semantic_error
        raise RpcError(f'RPC network request failed ({last}); check ETH_RPC_URLS')

    def many(self,calls,allow_errors=False):
        output=[None]*len(calls); missing=[]
        for i,(method,params) in enumerate(calls):
            path=self._path(method,params)
            if self.use_cache and path.exists():
                output[i]=json.loads(path.read_text()); self.hits+=1
            else: missing.append(i)
        for start in range(0,len(missing),self.batch_size):
            indexes=missing[start:start+self.batch_size]
            eligible=self.multicall and all(calls[i][0]=='eth_call' and len(calls[i][1])==2 for i in indexes)
            if eligible and len({calls[i][1][1] for i in indexes})==1:
                from .multicall import encode_aggregate,decode_aggregate
                try:
                    raw=self.one('eth_call',[{'to':'0xca11bde05977b3631167028862be2a173976ca11',
                        'data':encode_aggregate([calls[i][1][0] for i in indexes]),'gas':hex(25000000)},calls[indexes[0]][1][1]])
                except RpcError as aggregate_error:
                    if aggregate_error.kind in ('history_unavailable','authorization','rate_limit','network'):
                        if not allow_errors:raise
                        for i in indexes:output[i]={'rpc_error':{'message':str(aggregate_error)}}
                        continue
                    if len(indexes)>1:
                        mid=len(indexes)//2
                        for subgroup in (indexes[:mid],indexes[mid:]):
                            values=self.many([calls[i] for i in subgroup],allow_errors=allow_errors)
                            for i,value in zip(subgroup,values):output[i]=value
                    else:
                        i=indexes[0]
                        try:output[i]=self.one(*calls[i])
                        except RpcError as error:
                            if not allow_errors:raise
                            output[i]={'rpc_error':{'message':str(error)}}
                    continue
                results=decode_aggregate(raw)
                if len(results)!=len(indexes):raise RpcError('Multicall result count mismatch')
                for i,(ok,value) in zip(indexes,results):
                    if not ok:
                        if not allow_errors:output[i]=self.one(*calls[i])
                        else:output[i]={'rpc_error':{'message':'Multicall subcall reverted'}}
                    else:
                        output[i]=value
                        if self.use_cache and self.cache_individual:
                            path=self._path(*calls[i]);tmp=path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
                            tmp.write_text(json.dumps(value),encoding='utf-8');tmp.replace(path)
                continue
            payload=[{'jsonrpc':'2.0','id':i,'method':calls[i][0],'params':calls[i][1]} for i in indexes]
            response=self._post(payload)
            if not isinstance(response,list):
                response=[{'id':i,'error':response.get('error',{'message':'Batch response missing'})} for i in indexes]
            mapping={item['id']:item for item in response if isinstance(item,dict) and 'id' in item}
            for i in indexes:
                item=mapping.get(i,{})
                if 'error' in item or 'result' not in item or item.get('result') is None:
                    # Batch endpoints can return per-item rate limits even when HTTP succeeds.
                    # Retry independently through the configured fallback, never cache the error.
                    if error_kind(item.get('error',{}))=='rate_limit':time.sleep(1)
                    try:
                        output[i]=self.one(*calls[i]); continue
                    except RpcError as retry_error:
                        item={'error':{'message':str(retry_error)}}
                    error={'rpc_error':item.get('error',{'message':'Missing result'})}
                    if not allow_errors: raise RpcError(str(error))
                    output[i]=error
                else:
                    output[i]=item['result']
                    if self.use_cache and self.cache_individual:
                        path=self._path(*calls[i]); tmp=path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
                        tmp.write_text(json.dumps(output[i]),encoding='utf-8'); tmp.replace(path)
        return output

    def one(self,method,params,cache=True):
        cache=cache and self.use_cache
        path=self._path(method,params)
        if cache and path.exists():
            self.hits+=1
            return json.loads(path.read_text())
        result=self._post({'jsonrpc':'2.0','id':1,'method':method,'params':params})
        if 'error' in result: raise RpcError(str(result['error']))
        if result.get('result') is None: raise RpcError('Missing RPC result')
        if cache:
            tmp=path.with_suffix('.'+uuid.uuid4().hex+'.tmp'); tmp.write_text(json.dumps(result['result']),encoding='utf-8'); tmp.replace(path)
        return result['result']

    def block(self,n): return self.one('eth_getBlockByNumber',[hex(n),False])

    def block_at(self,timestamp,head):
        # Scope is post-Merge Ethereum. Public providers may prune pre-Merge blocks.
        lo,hi=15_537_394,head
        if timestamp<int(self.block(lo)['timestamp'],16):
            raise ValueError('Date predates supported post-Merge history')
        while lo<hi:
            mid=(lo+hi)//2
            if int(self.block(mid)['timestamp'],16)<timestamp: lo=mid+1
            else: hi=mid
        if int(self.block(lo)['timestamp'],16)<timestamp: raise ValueError('Date is after RPC head')
        return lo

    def logs(self,address,topics,start,end):
        try:
            result=self.one('eth_getLogs',[{'address':address,'topics':[topics],
                'fromBlock':hex(start),'toBlock':hex(end)}],cache=False)
            if not isinstance(result,list):raise RpcError('Invalid eth_getLogs result',kind='invalid_response')
            keys=set()
            for log in result:
                try:
                    key=(log['transactionHash'],int(log['logIndex'],16));block=int(log['blockNumber'],16)
                    valid=(start<=block<=end and log['address'].lower()==address.lower() and not log.get('removed')
                           and log['topics'] and log['topics'][0] in topics and key not in keys)
                except (KeyError,TypeError,ValueError):valid=False
                if not valid:raise RpcError('Invalid, duplicate, removed or out-of-range log; no checkpoint committed',kind='invalid_response')
                keys.add(key)
            if len(result) in (1000,2000,5000,10000,20000,32768,50000,65536,100000):
                if start==end:raise RpcError('Possible truncated single-block log response; use another RPC',kind='invalid_response')
                mid=(start+end)//2
                return self.logs(address,topics,start,mid)+self.logs(address,topics,mid+1,end)
            return result
        except RpcError as exc:
            if exc.kind!='range_limit' or start==end:raise
            mid=(start+end)//2
            return self.logs(address,topics,start,mid)+self.logs(address,topics,mid+1,end)

    def preflight(self,start,end,report_path,require_state=False):
        """Positive known-log + receipt probes, no cache; not proof of whole-range coverage."""
        fixtures=Path(__file__).resolve().parents[1]/'data/sources/rpc_history_probes.json'
        anchors=json.loads(fixtures.read_text(encoding='utf8'))
        selected=[p for p in anchors if start<=p['block']<=end]
        prior=[p for p in anchors if p['block']<=start]
        if prior:selected.insert(0,max(prior,key=lambda p:p['block']))
        if not selected:raise RpcError('No known historical probe at/before target range; add a verified probe first',kind='preflight')
        diagnostics=[];approved=[]
        for i,url in enumerate(self.urls,1):
            entry={'provider_id':i,'passed':False,'probes':[]}
            r=Rpc(self.cache/'preflight',urls=[url],timeout=12,retry_attempts=1)
            try:
                if int(r.one('eth_chainId',[],cache=False),16)!=1:raise RpcError('Expected Ethereum chain 1',kind='wrong_chain')
                for block in sorted({start,end}):
                    h=r.one('eth_getBlockByNumber',[hex(block),False],cache=False)
                    if not isinstance(h,dict) or int(h['number'],16)!=block:raise RpcError('Missing target boundary header')
                for p in selected:
                    b=p['block'];logs=r.one('eth_getLogs',[{'address':p['address'],'fromBlock':hex(b),'toBlock':hex(b)}],cache=False)
                    receipt=r.one('eth_getTransactionReceipt',[p['tx']],cache=False)
                    match=lambda l:l.get('transactionHash')==p['tx'] and int(l['logIndex'],16)==p['log_index'] and l['address'].lower()==p['address'] and int(l['blockNumber'],16)==b and not l.get('removed')
                    hit=next((l for l in logs if match(l)),None)
                    if hit is None or not any(match(l) and l['blockHash']==hit['blockHash'] for l in receipt['logs']):
                        raise RpcError('Known historical log missing or receipt mismatch; empty history quarantined',kind='incomplete_history')
                    entry['probes'].append({'block':b,'known_log_and_receipt_match':True})
                if require_state:
                    from .evm import calldata
                    value=r.one('eth_call',[{'to':anchors[0]['address'],'data':calldata('POOL_REVISION()')},hex(start)],cache=False)
                    if not isinstance(value,str) or len(value)!=66 or int(value,16)<1:raise RpcError('Historical eth_call probe failed')
                    entry['historical_state_probe']=True
                entry['passed']=True;approved.append(url)
            except (RpcError,ValueError,KeyError,TypeError) as exc:
                entry['failure_kind']=getattr(exc,'kind',error_kind(exc))
            diagnostics.append(entry);self.requests+=r.requests
        report={'start_block':start,'end_block':end,'require_state':require_state,'passed':bool(approved),'providers':diagnostics,
                'scope':'positive sample probes only; full coverage still requires crawl and independent audit'}
        report_path=Path(report_path);report_path.parent.mkdir(parents=True,exist_ok=True)
        report_path.write_text(json.dumps(report,indent=2),encoding='utf8')
        if not approved:raise RpcError('RPC preflight failed: no provider passed known-log/receipt checks. Set ETH_RPC_URLS to a history-capable Ethereum RPC, or use the shared audited dataset offline. See rpc_preflight.json. No new crawl coverage committed.',kind='preflight')
        self.urls=approved
        print(f'RPC preflight: {len(approved)}/{len(diagnostics)} providers passed; report: {report_path.name}',flush=True)
        return report
