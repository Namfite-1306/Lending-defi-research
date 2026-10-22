import hashlib
import json
import os
import re
import time
import urllib.request
import urllib.error
import uuid
from pathlib import Path

DEFAULT_RPC_URLS=('https://eth-mainnet.public.blastapi.io','https://eth.drpc.org','https://rpc.mevblocker.io')


def error_kind(error):
    text=str(error).lower()
    if any(x in text for x in ('4444','pruned','missing trie','historical state','archive requests','history unavailable')):return 'history_unavailable'
    if any(x in text for x in ('429','rate limit','compute units','too many requests')):return 'rate_limit'
    if any(x in text for x in ('401','403','unauthorized','personal token','api key','access denied')):return 'authorization'
    if any(x in text for x in ('block range','blocks range','range limit','maximum block','too many results','response size','query returned more','range too large')):return 'range_limit'
    if any(x in text for x in ('method not found','method_not','-32601','not support batch','not whitelisted')):return 'unsupported_method'
    if any(x in text for x in ('network','timeout','timed out','temporarily unavailable','502','503','504')):return 'network'
    return 'rpc_error'

class RpcError(RuntimeError):
    def __init__(self,message,failures=None,kind=None):
        super().__init__(message)
        if isinstance(failures,str) and kind is None:kind=failures;failures=None
        self.failures=failures or []
        self.kind=kind or error_kind(message)

class Rpc:
    def __init__(self, cache, urls=None, batch_size=20, multicall=False, cache_individual=True,timeout=35,retry_attempts=3):
        configured=urls if urls is not None else os.getenv('ETH_RPC_URLS',','.join(DEFAULT_RPC_URLS))
        if isinstance(configured,str):configured=configured.split(',')
        self.urls=list(dict.fromkeys(url.strip() for url in configured if url.strip()))
        if not self.urls:raise RpcError('ETH_RPC_URLS must contain at least one HTTP(S) RPC endpoint',kind='configuration')
        if batch_size<1:raise ValueError('RPC batch_size must be positive')
        self.cache=Path(cache)/'transport_v2'; self.cache.mkdir(parents=True,exist_ok=True)
        self.batch_size=batch_size; self.requests=0; self.hits=0
        self.multicall=multicall
        self.cache_individual=cache_individual
        self.timeout=timeout;self.retry_attempts=retry_attempts
        if timeout<=0 or retry_attempts<1:raise ValueError('RPC timeout and retry_attempts must be positive')
        self._unsupported_methods={}

    def _safe_message(self,message):
        message=str(message)
        for url in self.urls:message=message.replace(url,'[endpoint]')
        return re.sub(r'https?://[^\s\"\'<>]+','[endpoint]',message)[:240]

    @staticmethod
    def _method_denied(error):
        message=str(error.get('message','')).lower()
        return error.get('code')==-32601 or 'not whitelisted' in message or 'method not found' in message

    @staticmethod
    def _rate_limited(error):
        message=str(error.get('message','')).lower()
        return error.get('code')==429 or any(word in message for word in ('rate limit','compute units','too many requests'))

    @staticmethod
    def _failure_summary(failures):
        latest={row['endpoint']:row for row in failures}
        return '; '.join(f"endpoint #{i}: {row['code']} {row['message']}" for i,row in latest.items())

    def _path(self,method,params):
        key=json.dumps([method,params],sort_keys=True,separators=(',',':')).encode()
        return self.cache/(hashlib.sha256(key).hexdigest()+'.json')

    def _post(self,payload):
        # Endpoints/keys are never written to manifests or error messages.
        semantic_error=None;range_error=None;failures=[]
        method=payload.get('method') if isinstance(payload,dict) else None
        label=method or 'batch'

        def failed(endpoint,error,attempt):
            nonlocal semantic_error,range_error
            if error_kind(error)=='range_limit':range_error={'error':error}
            semantic_error={'error':error}
            failures.append({'endpoint':endpoint,'code':error.get('code','RPC'),
                             'message':self._safe_message(error.get('message','RPC error')),'attempt':attempt+1})

        for attempt in range(self.retry_attempts):
            transient=False
            for endpoint,url in enumerate(self.urls,1):
                if method and (url,method) in self._unsupported_methods:
                    failed(endpoint,self._unsupported_methods[url,method],attempt)
                    continue
                try:
                    req=urllib.request.Request(url,json.dumps(payload).encode(),
                        {'Content-Type':'application/json','User-Agent':'DeFiResearch/1.0'})
                    self.requests+=1
                    with urllib.request.urlopen(req,timeout=self.timeout) as response:
                        result=json.load(response)
                    if self.requests % 25 == 0:
                        print(f'RPC progress: {self.requests} HTTP requests, {self.hits} cache hits',flush=True)
                    time.sleep(.08)
                    if not isinstance(result,(dict,list)) or (isinstance(result,list) and not isinstance(payload,list)):
                        failed(endpoint,{'message':'Malformed RPC response'},attempt);continue
                    if isinstance(result,dict) and 'error' in result:
                        error=result['error'];failed(endpoint,error,attempt)
                        if method and self._method_denied(error):self._unsupported_methods[url,method]=error
                        transient=transient or self._rate_limited(error)
                        continue
                    if isinstance(result,dict) and result.get('result') is None:
                        failed(endpoint,{'message':'Missing RPC result'},attempt);continue
                    return result
                except urllib.error.HTTPError as exc:
                    # A JSON-RPC error can arrive with HTTP 400/403/429. Preserve it;
                    # hiding it caused oversized queries to fall through to pruned providers.
                    parsed=False
                    try:
                        error=json.loads(exc.read())
                        if isinstance(error,dict) and 'error' in error:
                            error=error['error'];failed(endpoint,error,attempt);parsed=True
                            if method and self._method_denied(error):self._unsupported_methods[url,method]=error
                            transient=transient or self._rate_limited(error)
                    except (ValueError,UnicodeError):pass
                    if not parsed:
                        failures.append({'endpoint':endpoint,'code':exc.code,'message':'HTTP request rejected','attempt':attempt+1})
                    transient=transient or exc.code==429 or exc.code>=500
                except Exception as exc:
                    failures.append({'endpoint':endpoint,'code':'network','message':type(exc).__name__,'attempt':attempt+1})
                    transient=True
            # Keep retries for any recoverable provider failure even if the final
            # provider rejects the method. A final whitelist error is not the cause
            # of earlier timeouts or rate limits.
            if not transient:break
            if attempt+1<self.retry_attempts:time.sleep(.5*(2**attempt))
        if semantic_error is not None:return {**(range_error or semantic_error),'_rpc_failures':failures}
        raise RpcError(f'RPC network request failed for {label}: {self._failure_summary(failures)}; check ETH_RPC_URLS',failures)

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
                        if self.cache_individual:
                            path=self._path(*calls[i]);tmp=path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
                            tmp.write_text(json.dumps(value),encoding='utf-8');tmp.replace(path)
                continue
            payload=[{'jsonrpc':'2.0','id':i,'method':calls[i][0],'params':calls[i][1]} for i in indexes]
            response=self._post(payload)
            # A provider can reject batches or fail only some historical calls.
            # Retry failed items singly so _post can try every configured endpoint.
            mapping={item['id']:item for item in response if isinstance(item,dict) and 'id' in item} if isinstance(response,list) else {}
            for i in indexes:
                item=mapping.get(i,{})
                if 'error' in item or 'result' not in item or item.get('result') is None:
                    if item.get('error',{}).get('code') in (429,-32005,-32016):
                        time.sleep(1)
                    try:
                        output[i]=self.one(*calls[i],cache=self.cache_individual)
                    except RpcError as exc:
                        if not allow_errors: raise
                        output[i]={'rpc_error':{'message':str(exc)}}
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
        if 'error' in result:
            failures=result.get('_rpc_failures',[])
            detail=self._failure_summary(failures) if failures else self._safe_message(result['error'])
            raise RpcError(f'{method} failed: {detail}. Check ETH_RPC_URLS: endpoints must allow this method and historical state at the requested block.',failures,kind=error_kind(result['error']))
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
