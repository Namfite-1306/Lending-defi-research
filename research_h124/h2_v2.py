"""Conservative Comet validation: end-block index, borrower-specific ordering.

End-block state is VALIDATION evidence only, never a predictor. An earlier
debt-changing event involving the borrower still requires transaction replay.
"""
import json
from decimal import Decimal as D
from defi_data.pipeline import CONTRACTS,call_request
from defi_data.evm import words,uint,addr
from defi_data.rpc import Rpc
from .v2_common import *

def run(all_episodes=False):
    out=OUT/('h2_full_validation' if all_episodes else 'h2');out.mkdir(parents=True,exist_ok=True)
    episodes=read(V1_OUT/'h2/episodes.csv');by={r['episode']:r for r in episodes}
    selected=read(V1_OUT/'h2/archive_state_validation.csv') if not all_episodes else [{'episode':r['episode'],'status':'not_in_original_sample'} for r in episodes if r['protocol']=='compound_v3_usdc'];c=connect()
    rpc=Rpc(DATA/'h2/rpc',batch_size=80,multicall=True,timeout=12,retry_attempts=1)
    market=CONTRACTS['compound_v3_usdc'][0];scale=int(load(H1_DATA/'h2/normalization_provenance.json')['base_index_scale']);checks=[]
    if all_episodes:
        requests=[];seen=set()
        for old in selected:
            e=by[old['episode']];b=int(e['block'])
            for request in [call_request(market,'userBasic(address)',[e['borrower']],b-1),call_request(market,'totalsBasic()',[],b)]:
                key=json.dumps(request,sort_keys=True)
                if key not in seen:seen.add(key);requests.append(request)
        for start in range(0,len(requests),80):rpc.many(requests[start:start+80],allow_errors=True)
    for old in selected:
        e=by[old['episode']];b=int(e['block']);account=e['borrower'];idx=int(e['logidx'])
        events=list(c.execute("SELECT txidx,idx,name,decoded FROM events WHERE protocol='compound_v3_usdc' AND block=? ORDER BY txidx,idx",(b,)))
        target=c.execute('SELECT txidx FROM events WHERE tx=? AND idx=?',(e['tx'],idx)).fetchone()[0]
        related=[]
        for txidx,logidx,name,raw in events:
            if (txidx,logidx)>=(target,idx) or name not in ['Supply','Withdraw','Transfer','AbsorbDebt']:continue
            d=json.loads(raw)
            if account in [str(v).lower() for v in d.values()]:related.append((txidx,logidx,name))
        row={'episode':e['episode'],'block':b,'borrower':account,'prior_borrower_debt_events':len(related),'old_status':old['status']}
        if related:row.update(status='requires_intra_transaction_replay');checks.append(row);continue
        try:
            basic,totals=rpc.many([call_request(market,'userBasic(address)',[account],b-1),call_request(market,'totalsBasic()',[],b)])
            principal=uint(words(basic)[0]);principal=principal-2**256 if principal>=2**255 else principal
            if principal>=0:raise ValueError('No pre-block negative principal')
            index=uint(words(totals)[1]);nominal=(-principal)*index
            lo=nominal//scale;hi=(nominal+scale-1)//scale;eventlo=int(e['debt_raw_lower_bound']);eventhi=int(e['debt_raw_upper_estimate'])
            overlap=max(lo,eventlo)<=min(hi,eventhi)
            row.update(status='interval_overlap' if overlap else 'mismatch_requires_replay',passed=overlap,preblock_principal=str(principal),
              endblock_borrow_index=str(index),state_debt_low=str(lo),state_debt_high=str(hi),event_debt_low=str(eventlo),event_debt_high=str(eventhi))
        except Exception as exc:row.update(status='source_error',kind=getattr(exc,'kind',type(exc).__name__))
        checks.append(row)
    c.close();write(out/'borrower_order_validation.csv',checks)
    com=[e for e in episodes if e['protocol']=='compound_v3_usdc'];blocks=sorted({int(e['block']) for e in com});slot='0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc'
    fingerprints=[]
    for offset in range(0,len(blocks),80):
        group=blocks[offset:offset+80]
        try:
            values=rpc.many([('eth_getStorageAt',[market,slot,hex(b)]) for b in group])
            for b,value in zip(group,values):fingerprints.append({'block':b,'implementation':addr(value[2:]),'validated_semantics':False})
        except Exception as exc:
            fingerprints.extend({'block':b,'status':'source_error','kind':getattr(exc,'kind',type(exc).__name__)} for b in group)
    write(out/'comet_implementation_fingerprints.csv',fingerprints)
    # Keep values and their measurement definitions identical to v1; fresh checks
    # do not retrospectively redefine published concentration denominators.
    sensitivity=read(V1_OUT/'h2/matched_concentration_sensitivity.csv')
    coverage=read(V1_OUT/'h2/matched_coverage.csv');write(out/'matched_concentration_sensitivity.csv',sensitivity);write(out/'matched_coverage.csv',coverage)
    paid=sum(int(e['base_paid_out_raw']) for e in com);credit=sum(int(e['supply_credit_raw']) for e in com)
    assert all(int(e['base_paid_out_raw'])==int(e['supply_credit_raw'])+int(e['debt_raw_upper_estimate']) for e in com)
    result={'updated_utc':now(),'status':'validated_with_semantic_limits','selected':len(checks),'passed':sum(r.get('passed') is True for r in checks),
      'remaining_replay':sum(r['status']=='requires_intra_transaction_replay' for r in checks),'mismatches':sum(r.get('passed') is False for r in checks),
      'errors':sum(r['status']=='source_error' for r in checks),'fingerprinted_blocks':len(fingerprints),'implementation_addresses':sorted({r['implementation'] for r in fingerprints if 'implementation' in r}),
      'credit_fraction_of_basePaidOut':credit/paid,'source_hashes':{name:digest(V1_OUT/'h2'/name) for name in ['episodes.csv','collateral_legs.csv','matched_concentration_sensitivity.csv']},
      'validation_scope':'all observed Comet episodes' if all_episodes else '64 selected samples',
      'limitations':['End-block index used for validation only; no prediction lookahead','Borrower has no earlier observed debt-changing logs; unlogged calls and all-upgrade semantics not proven',
        'Implementation fingerprints are not bytecode semantic verification','Prior-block pricing and financing differences preserved; price-age coverage remains a limitation']}
    save(out/'summary.json',result);print(json.dumps(result,ensure_ascii=False),flush=True);return result
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--all-episodes',action='store_true');a=p.parse_args();run(a.all_episodes)
