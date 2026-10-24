"""Decode configuration history with the union of released historical ABIs."""
import json,urllib.request,hashlib
from collections import Counter
from .recovery import RUN,OUT
from .expansion import read_csv
from .evm import parse_events,decode_event,topic,addr,words,uint
from .pipeline import csv_write,save_json
def main():
    specs={};sources=[]
    for tag in ['v3.1.0','v3.2.0','v3.3.0','v3.4.0','v3.5.0','v3.6.0']:
        path=RUN/f'IPoolConfigurator_{tag}.sol';url=f'https://raw.githubusercontent.com/aave-dao/aave-v3-origin/{tag}/src/contracts/interfaces/IPoolConfigurator.sol'
        try:
            if not path.exists():path.write_bytes(urllib.request.urlopen(url,timeout=20).read())
            source=path.read_text(encoding='utf8');sources.append({'tag':tag,'url':url,'sha256':hashlib.sha256(source.encode()).hexdigest()})
        except Exception as e:sources.append({'tag':tag,'url':url,'error':str(e)[:200]})
    for path in sorted(RUN.glob('IPoolConfigurator*.sol')):
        for name,spec in parse_events(path.read_text(encoding='utf8')).items():specs[spec['topic']]=(name,spec)
    raw=[json.loads(l) for l in (RUN/'configuration_logs.jsonl').read_text(encoding='utf8').splitlines()]
    bykey={(l['transactionHash'],int(l['logIndex'],16)):l for l in raw};rows=read_csv(OUT/'configuration_timeline.csv')
    for r in rows:
        if r['contract_role']=='configurator' and r['topic0']==topic('Upgraded(address)'):
            r['event']='ConfiguratorUpgraded';r['decoded']=json.dumps({'implementation':addr(bykey[r['tx'],int(r['logidx'])]['topics'][1])})
        if r['contract_role']=='configurator' and r['topic0'] in specs:
            name,spec=specs[r['topic0']]
            try:
                decoded=decode_event(bykey[r['tx'],int(r['logidx'])],spec)
                if name=='ReserveInterestRateDataChanged' and len(words(decoded['data']))==4:
                    decoded['data_words_uint']=list(map(uint,words(decoded['data'])))
                r['decoded']=json.dumps(decoded);r['event']=name
            except Exception as e:r['event']='ABI_mismatch:'+name
    csv_write(OUT/'configuration_timeline.csv',rows);save_json(RUN/'historical_configuration_abis.json',sources)
    print(Counter(r['event'] for r in rows if r['contract_role']=='configurator'),flush=True)
if __name__=='__main__':main()
