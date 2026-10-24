"""Probe documented/public RPC access; record refusals rather than infer missing traces."""
from concurrent.futures import ThreadPoolExecutor
import json
from .recovery import RUN,http
from .pipeline import save_json
TX='0xec016dd36a9d6dc9880321e461f61febdf8fd610071d494b9228916b7e7a8031'
URLS=['https://eth-mainnet.public.blastapi.io','https://eth.drpc.org','https://ethereum-rpc.publicnode.com','https://1rpc.io/eth',
      'https://eth.blockrazor.xyz','https://eth.merkle.io','https://rpc.payload.de','https://ethereum.gateway.tenderly.co']
def main():
    def probe(pair):
        i,url=pair;output={'provider_id':i,'methods':[]}
        for method,params in [('debug_traceTransaction',[TX,{'tracer':'callTracer'}]),('trace_transaction',[TX])]:
            try:
                result=http(url,method,params)
                if not result:raise ValueError('Empty trace is not proof of no calls')
                save_json(RUN/'trace_probes'/f'provider_{i}_{method}.json',result)
                output['methods'].append({'method':method,'available':True,'result_type':type(result).__name__})
            except Exception as e:output['methods'].append({'method':method,'available':False,'error':str(e)[:300]})
        print(json.dumps(output,ensure_ascii=True),flush=True);return output
    with ThreadPoolExecutor(max_workers=4) as ex:results=list(ex.map(probe,enumerate(URLS)))
    save_json(RUN/'trace_provider_diagnosis.json',results)
if __name__=='__main__':main()
