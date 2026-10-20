import hashlib
import json
import os
import time
import urllib.request
import urllib.error
import uuid
from pathlib import Path

class RpcError(RuntimeError): pass

class Rpc:
    def __init__(self, cache, urls=None, batch_size=20, multicall=False, cache_individual=True):
        self.urls=urls or os.getenv('ETH_RPC_URLS','https://eth-mainnet.public.blastapi.io,https://rpc.flashbots.net').split(',')
        self.cache=Path(cache); self.cache.mkdir(parents=True,exist_ok=True)
        self.batch_size=batch_size; self.requests=0; self.hits=0
        self.multicall=multicall
        self.cache_individual=cache_individual

    def _path(self,method,params):
        key=json.dumps([method,params],sort_keys=True,separators=(',',':')).encode()
        return self.cache/(hashlib.sha256(key).hexdigest()+'.json')

    def _post(self,payload):
        # Endpoints/keys are never written to manifests or error messages.
        last=''; semantic_error=None
        for attempt in range(3):
            transient=False
            for url in self.urls:
                try:
                    req=urllib.request.Request(url,json.dumps(payload).encode(),
                        {'Content-Type':'application/json','User-Agent':'DeFiResearch/1.0'})
                    with urllib.request.urlopen(req,timeout=35) as response:
                        result=json.load(response)
                    self.requests+=1
                    if self.requests % 25 == 0:
                        print(f'RPC progress: {self.requests} HTTP requests, {self.hits} cache hits',flush=True)
                    time.sleep(.08)
                    if isinstance(result,dict) and 'error' in result:
                        semantic_error=result
                        msg=str(result['error']).lower()
                        transient=transient or any(x in msg for x in ('429','rate limit','compute units','too many requests'))
                        continue
                    return result
                except urllib.error.HTTPError as exc:
                    # A JSON-RPC error can arrive with HTTP 400/403/429. Preserve it;
                    # hiding it caused oversized queries to fall through to pruned providers.
                    try:
                        error=json.loads(exc.read())
                        if isinstance(error,dict) and 'error' in error:
                            semantic_error=error
                            transient=transient or exc.code==429
                    except (ValueError,UnicodeError):pass
                    last=f'HTTP {exc.code}'
                except Exception as exc: last=type(exc).__name__
            if semantic_error is not None:
                err=semantic_error.get('error',{})
                message=str(err.get('message','')).lower()
                if not transient and err.get('code') not in (429,) and not any(x in message for x in ('rate limit','compute units','too many requests')):
                    return semantic_error
            time.sleep(.5*(2**attempt))
        if semantic_error is not None:return semantic_error
        raise RpcError(f'RPC network request failed ({last}); check ETH_RPC_URLS')

    def many(self,calls,allow_errors=False):
        output=[None]*len(calls); missing=[]
        for i,(method,params) in enumerate(calls):
            path=self._path(method,params)
            if path.exists():
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
                except RpcError:
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
                        if self.cache_individual:
                            path=self._path(*calls[i]);tmp=path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
                            tmp.write_text(json.dumps(value),encoding='utf-8');tmp.replace(path)
                continue
            payload=[{'jsonrpc':'2.0','id':i,'method':calls[i][0],'params':calls[i][1]} for i in indexes]
            response=self._post(payload)
            if not isinstance(response,list):
                raise RpcError('RPC provider does not support batches; use another endpoint')
            mapping={item['id']:item for item in response}
            for i in indexes:
                item=mapping.get(i,{})
                if 'error' in item or 'result' not in item or item.get('result') is None:
                    # Batch endpoints can return per-item rate limits even when HTTP succeeds.
                    # Retry independently through the configured fallback, never cache the error.
                    if item.get('error',{}).get('code') in (429,-32005,-32016):
                        time.sleep(1)
                        try:
                            output[i]=self.one(*calls[i]); continue
                        except RpcError:
                            pass
                    error={'rpc_error':item.get('error',{'message':'Missing result'})}
                    if not allow_errors: raise RpcError(str(error))
                    output[i]=error
                else:
                    output[i]=item['result']
                    path=self._path(*calls[i]); tmp=path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
                    tmp.write_text(json.dumps(output[i]),encoding='utf-8'); tmp.replace(path)
        return output

    def one(self,method,params,cache=True):
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
            return self.one('eth_getLogs',[{'address':address,'topics':[topics],
                'fromBlock':hex(start),'toBlock':hex(end)}])
        except RpcError as exc:
            if any(x in str(exc).lower() for x in ('network request failed','execution reverted','pruned','personal token','unauthorized','archive requests')): raise
            if start==end: raise
            mid=(start+end)//2
            return self.logs(address,topics,start,mid)+self.logs(address,topics,mid+1,end)
