"""Small unauthenticated public RPC probes. Never reads account RPC env vars."""
import concurrent.futures,json,urllib.request
from decimal import Decimal
from defi_data.evm import calldata
from .common import *

URLS=['https://ethereum-rpc.publicnode.com','https://eth.llamarpc.com','https://eth.drpc.org','https://1rpc.io/eth']

def probe(url):
    results=[]
    def call(method,params):
        req=urllib.request.Request(url,data=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}).encode(),headers={'Content-Type':'application/json','User-Agent':'DeFiResearch/1.0'})
        with urllib.request.urlopen(req,timeout=10) as response:value=json.load(response)
        if 'error' in value:raise ValueError(str(value['error'])[:160])
        return value['result']
    for quarter in ['2023Q1','2026Q1']:
        folder=ROOT/'data/research_h124_20261024/h1'/quarter
        scope=load(folder/'scope.json');r=read(folder/'validation.csv')[0]
        row={'endpoint':url,'quarter':quarter,'block':scope['block'],'method':'eth_getBlockByNumber + historical eth_call','paid_or_account':False}
        try:
            header=call('eth_getBlockByNumber',[hex(scope['block']),False])
            if not header or header['hash'].lower()!=scope['hash'].lower():raise ValueError('Historical block hash mismatch')
            value=call('eth_call',[{'to':scope['pool'],'data':calldata('getUserAccountData(address)',r['account'])},hex(scope['block'])])
            if not value.startswith('0x') or len(value)!=386:raise ValueError('Historical account ABI not six words')
            hf=Decimal(int(value[2+5*64:2+6*64],16))/10**18
            error=abs(hf-Decimal(r['hf_reported']))/max(abs(Decimal(r['hf_reported'])),Decimal('1e-12'))
            row.update(status='matched' if error<=Decimal('1e-4') else 'mismatch',relative_hf_error=float(error))
        except Exception as exc:row.update(status='unavailable',reason=str(exc)[:180])
        results.append(row)
    return results

def run():
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        rows=[r for group in pool.map(probe,URLS) for r in group]
    result={'updated_utc':now(),'samples':rows,'matched_samples':sum(r['status']=='matched' for r in rows),'sample_only':True,
      'account_or_paid_source_used':False,'remaining':'Two account/block probes per endpoint do not verify the full historical census. If unavailable, archive state is still required; no paid RPC was used.'}
    save(OUT/'source_probe.json',result);print('PUBLIC RPC PROBE',result['matched_samples'],'/',len(rows),flush=True)
    return result

if __name__=='__main__':run()
