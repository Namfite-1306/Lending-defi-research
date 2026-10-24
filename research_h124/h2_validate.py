"""Archive-state spot checks of Comet credit-corrected debt intervals."""
import json
from pathlib import Path
import numpy as np
from defi_data.rpc import Rpc
from defi_data.pipeline import CONTRACTS,call_request
from defi_data.evm import words,uint
from .common import DATA,OUT,read,write,save,connect,now

def run():
    rows=[r for r in read(OUT/'h2/episodes.csv') if r['protocol']=='compound_v3_usdc'];rows.sort(key=lambda r:(int(r['block']),int(r['logidx'])))
    chosen={r['episode']:r for r in [rows[i] for i in np.linspace(0,len(rows)-1,48).astype(int)]+sorted(rows,key=lambda r:-int(r['debt_raw_upper_estimate']))[:16]}
    rpc=Rpc(DATA/'h2/state_validation_rpc',batch_size=50,multicall=True,timeout=12,retry_attempts=1);market=CONTRACTS['compound_v3_usdc'][0]
    c=connect();output=[];scale=int(json.loads((DATA/'h2/normalization_provenance.json').read_text())['base_index_scale'])
    for r in chosen.values():
        block=int(r['block']);account=r['borrower'];txidx=c.execute('SELECT txidx FROM events WHERE tx=? AND idx=?',(r['tx'],int(r['logidx']))).fetchone()[0]
        prior=c.execute("SELECT count(*) FROM events WHERE protocol='compound_v3_usdc' AND block=? AND txidx<?",(block,txidx)).fetchone()[0]
        row={'episode':r['episode'],'block':block,'borrower':account,'selection':'48 evenly spaced + 16 largest, deduplicated','prior_selected_comet_logs_in_block':prior}
        if prior:row['status']='requires_intra_block_replay';output.append(row);continue
        try:
            calls=[call_request(market,sig,args,block-1) for sig,args in [('userBasic(address)',[account]),('totalsBasic()',[]),('getUtilization()',[])]]
            basic,totals,util=rpc.many(calls);principal=uint(words(basic)[0]);principal=principal-2**256 if principal>=2**255 else principal
            if principal>=0:raise ValueError('No negative pre-block principal; transaction replay required')
            w=words(totals);idx=uint(w[1]);elapsed=int(r['stamp'])-uint(w[6])
            if elapsed<0:raise ValueError('Future accrual timestamp')
            rate=uint(words(rpc.one(*call_request(market,'getBorrowRate(uint256)',[uint(words(util)[0])],block-1)))[0])
            new_index=idx+idx*rate*elapsed//10**18;nominal=(-principal)*new_index
            expected_low=nominal//scale;expected_high=(nominal+scale-1)//scale
            debt_low=int(r['debt_raw_lower_bound']);debt_high=int(r['debt_raw_upper_estimate']);overlap=max(expected_low,debt_low)<=min(expected_high,debt_high)
            row.update(status='overlapping_intervals' if overlap else 'mismatch_requires_trace',preblock_principal=str(principal),accrued_borrow_index=str(new_index),
              state_debt_lower=str(expected_low),state_debt_upper=str(expected_high),event_debt_lower=str(debt_low),event_debt_upper=str(debt_high),passed_interval_overlap=overlap)
        except Exception as exc:row.update(status='error',error_kind=getattr(exc,'kind',type(exc).__name__),error=str(exc)[:150])
        output.append(row)
    c.close();write(OUT/'h2/archive_state_validation.csv',output)
    save(OUT/'h2/archive_state_validation.json',{'generated_utc':now(),'selected':len(output),'passed':sum(r.get('passed_interval_overlap') is True for r in output),
      'mismatches':sum(r.get('passed_interval_overlap') is False for r in output),'requires_intra_block':sum(r['status']=='requires_intra_block_replay' for r in output),
      'errors':sum(r['status']=='error' for r in output),'scope':'Pre-block principal/index accrued to event timestamp; excludes known earlier selected Comet logs in block',
      'limitations':['Not full intra-transaction trace verification','Unlogged earlier market calls may exist','Cannot prove implementation equivalence across all upgrades']})
    # Check block/date assertions from the publicly uploaded SSRN-related preprint.
    checks=[]
    for block,claimed in [(16308190,'2023-01-01'),(21525600,'2025-12-31')]:
        h=rpc.block(block);actual=__import__('datetime').datetime.fromtimestamp(int(h['timestamp'],16),__import__('datetime').timezone.utc).isoformat()
        checks.append({'block':block,'claimed_date':claimed,'actual_timestamp_utc':actual,'date_matches':actual[:10]==claimed,'hash':h['hash']})
    save(OUT/'literature/ssrn_preprint_block_date_check.json',{'scope':'Author-uploaded ResearchGate preprint, not verified identical to July SSRN revision','checks':checks})
    print('Comet state validation',len(output),'cases; matches',sum(r.get('passed_interval_overlap') is True for r in output),flush=True)
if __name__=='__main__':run()
