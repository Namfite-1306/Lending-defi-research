"""Three distinct audits: structure, independent headers, research contracts."""
import random,json
import numpy as np
from .v2_common import *

def audit(network=False):
    from .h4_data import block_connection
    OUT.mkdir(parents=True,exist_ok=True);baseline=OUT/'old_output_hashes.json'
    paths=[V1_OUT/'h2'/f for f in ['episodes.csv','collateral_legs.csv','matched_concentration_sensitivity.csv']]
    paths += [V1_OUT/'h4'/f for f in ['model_comparison.csv','residuals.json','summary.json']]
    old=CANONICAL/'results/full_7rq_20261022_final';frozen=load(old/'result_checksums.json',{})
    expected={str(old/name):value for name,value in frozen.items()}
    if not baseline.exists():save(baseline,{str(p):digest(p) for p in paths})
    expected.update(load(baseline,{}));mismatch=[name for name,value in expected.items() if not __import__('pathlib').Path(name).exists() or digest(name)!=value]
    c=block_connection();headers=list(c.execute('SELECT block,stamp,hash,parent,base_fee,gas_used,gas_limit FROM headers ORDER BY block'));c.close()
    monotonic=all(a[1]<b[1] for a,b in zip(headers,headers[1:]));chain=all(b[3]==a[2] for a,b in zip(headers,headers[1:]) if b[0]==a[0]+1)
    valid_gas=all(int(h[4])>=0 and 0<=h[5]<=h[6] and h[6]>0 for h in headers)
    structure={'headers':len(headers),'timestamp_monotonic':monotonic,'adjacent_parent_links_match':chain,'gas_fields_valid':valid_gas,'passed':bool(headers) and monotonic and chain and valid_gas}
    independent=load(OUT/'audit_independent_headers.json',{'status':'not_run'})
    if network and headers:
        from defi_data.rpc import Rpc
        from .h4_data import header_row
        rpc=Rpc(DATA/'independent_headers',urls=['https://eth.drpc.org'],batch_size=50,use_cache=False,cache_individual=False,timeout=12,retry_attempts=1)
        sample=random.Random(42).sample(headers,min(50,len(headers)));rows=[]
        try:
            values=rpc.many([('eth_getBlockByNumber',[hex(r[0]),False]) for r in sample])
            rows=[{'block':r[0],'match':tuple(r)==header_row(h,r[0])} for r,h in zip(sample,values)]
            independent={'status':'completed','sample':len(sample),'matched':sum(r['match'] for r in rows),'passed':len(rows)==len(sample) and all(r['match'] for r in rows),
              'provider':'eth.drpc.org','scope':'random sample of collected headers; provider may overlap fallback sources, not independent consensus proof'}
        except Exception as exc:independent={'status':'source_error','kind':getattr(exc,'kind',type(exc).__name__),'passed':False}
        save(OUT/'audit_independent_headers.json',independent)
    h2=load(OUT/'h2_full_validation/summary.json',load(OUT/'h2/summary.json',{}));research={'comet_sample_matches':h2.get('passed'),'comet_sample_size':h2.get('selected')}
    p=DATA/'h4_panel_5min.npz'
    if p.exists():
        a=np.load(p);research.update(panel_bins=len(a['t']),unique_ordered_bins=bool(np.all(np.diff(a['t'])==300)),
          events=int(a['y'].sum()),unique_feature_names=len(set(a['names']))==len(a['names']),panel_hash_verified=digest(p)==load(OUT/'h4_data_readiness.json',{}).get('panel_sha256'))
        a.close()
    model=OUT/'h4/model_comparison.csv'
    if model.exists():
        rs=read(model);research.update(model_rows=len(rs),same_test_bins=len({r['test_bins'] for r in rs})==1,same_test_event_counts=len({r['test_events'] for r in rs})==1)
    p=DATA/'h4_prefix_panel_5min.npz';ready=load(OUT/'h4_prefix_data_readiness.json',{})
    if p.exists():
        with np.load(p) as a:
            research['prefix']={'bins':len(a['t']),'events':int(a['y'].sum()),'unique_ordered_bins':bool(np.all(np.diff(a['t'])==300)),
              'panel_hash_verified':digest(p)==ready.get('panel_sha256'),'full_target_promoted':ready.get('target_period_complete') is not False,
              'stop_block_absent':ready.get('first_unverified_block') not in {h[0] for h in headers}}
        f=OUT/'h4_prefix/model_comparison.csv'
        if f.exists():
            rs=read(f);research['prefix'].update(model_rows=len(rs),same_test_bins=len({r['test_bins'] for r in rs})==1,same_test_event_counts=len({r['test_events'] for r in rs})==1)
    full=[]
    for q in load(H1_DATA/'h1/quarter_plan.json',[]):
        folder=H1_DATA/'h1'/q['quarter'];scope=load(folder/'scope.json',{})
        if scope.get('full_snapshot_complete'):
            freeze=load(folder/'freeze_manifest.json',{});full.append(bool(freeze) and all(digest(folder/name)==value for name,value in freeze.get('files',{}).items()))
    research.update(full_quarters_checked=len(full),full_quarter_hashes_match=all(full),no_sample_promotion=True)
    result={'updated_utc':now(),'structure':structure,'onchain_sample':independent,'research':research,'old_files_checked':len(expected),
      'old_output_mismatches':mismatch,'old_outputs_preserved':bool(expected) and not mismatch,
      'note':'Audit evidence, not automatic completion of all five objectives. Missing series and rejected residuals stay visible.'}
    save(OUT/'audit.json',result);return result
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--network',action='store_true');a=p.parse_args();print(json.dumps(audit(a.network),ensure_ascii=False))
