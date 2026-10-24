"""Point-in-time recursive leverage candidates; high-precision receipt evidence stays separate."""
import argparse,bisect,csv,json,zlib
from collections import defaultdict,Counter
from itertools import groupby
from .recovery import RUN,OUT,OLD,database
from .pipeline import ROOT,CONTRACTS,csv_write,save_json,utc,ts,call,call_request
from .expansion import read_csv,signed
from .evm import topic,words,uint,addr,parse_events,decode_event
from .rpc import Rpc

def motifs(events,hours,end_stamp):
    """O(n log n), earliest supply then next same-token borrow; no Cartesian multiplication."""
    supplies=[i for i,e in enumerate(events) if e['name']=='Supply'];borrows=defaultdict(list)
    for i,e in enumerate(events):
        if e['name']=='Borrow':borrows[e['token']].append(i)
    for i,e in enumerate(events):
        if e['name']!='Borrow':continue
        si=bisect.bisect_right(supplies,i)
        if si==len(supplies):continue
        j=supplies[si];indices=borrows[e['token']];ri=bisect.bisect_right(indices,j)
        if ri==len(indices):continue
        k=indices[ri]
        if events[k]['stamp']-e['stamp']>hours*3600:continue
        yield {'account':e['account'],'window_hours':hours,'borrow_tx':e['tx'],'borrow_idx':e['idx'],
          'supply_tx':events[j]['tx'],'supply_idx':events[j]['idx'],'reborrow_tx':events[k]['tx'],'reborrow_idx':events[k]['idx'],
          'borrow_token':e['token'],'supply_token':events[j]['token'],'borrow_stamp':e['stamp'],
          'label_available_at':utc(events[k]['stamp']),'right_censored':e['stamp']+hours*3600>end_stamp,
          'verified_recursive':False,'label':'temporal_motif_not_funding_proof'}

def all_history_labels():
    OUT.mkdir(parents=True,exist_ok=True);c=database();end=ts('2026-10-01T00:00:00Z')
    # This index is built after ingestion, not on every insertion.
    c.execute('CREATE INDEX IF NOT EXISTS events_account_order ON events(protocol,account,block,txidx,idx)');c.commit()
    fields=['account','window_hours','borrow_tx','borrow_idx','supply_tx','supply_idx','reborrow_tx','reborrow_idx','borrow_token','supply_token',
            'borrow_stamp','label_available_at','right_censored','verified_recursive','label']
    stats={h:Counter() for h in (6,24,48)};candidate_keys=set();controls=[]
    with (OUT/'recursive_candidates_full_history.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        cursor=c.execute("SELECT account,block,txidx,idx,tx,stamp,name,token FROM events WHERE protocol='aave_v3' AND name IN ('Borrow','Supply') ORDER BY account,block,txidx,idx")
        for a,group in groupby(cursor,key=lambda r:r[0]):
            es=[dict(zip(['account','block','txidx','idx','tx','stamp','name','token'],r)) for r in group]
            for h in stats:
                result=list(motifs(es,h,end));writer.writerows(result)
                positives={(r['borrow_tx'],r['borrow_idx']) for r in result}
                stats[h]['motifs']+=len(result);stats[h]['uncensored_motifs']+=sum(not r['right_censored'] for r in result)
                stats[h]['censored_motifs']+=sum(r['right_censored'] for r in result)
                for e in es:
                    if e['name']!='Borrow':continue
                    if e['stamp']+h*3600<=end:
                        stats[h]['eligible_starts']+=1
                        if (e['tx'],e['idx']) not in positives:
                            stats[h]['no_observed_motif']+=1
                            if len(controls)<600:controls.append({'account':a,'borrow_tx':e['tx'],'borrow_idx':e['idx'],'window_hours':h,
                                'classification':'no observed Aave motif; NOT proof of no external leverage','label_available_at':utc(e['stamp']+h*3600)})
    csv_write(OUT/'recursive_sensitivity_full_history.csv',[{'window_hours':h,**dict(v),'verified_labels':'see receipt verification; temporal counts are not verified labels'} for h,v in stats.items()])
    csv_write(OUT/'recursive_negative_controls_sample.csv',controls);c.close()

def flow_sample():
    OUT.mkdir(parents=True,exist_ok=True);rpc=Rpc(ROOT/'data/rpc_cache',batch_size=5)
    cs=read_csv(OLD/'processed/recursive_window_candidates.csv');unique={}
    for r in cs:
        if r['borrow_tx']==r['supply_tx']==r['reborrow_tx']:unique.setdefault((r['borrow_tx'],r['account']),r)
    selected=list(unique.values())[:80];specs=parse_events((ROOT/'data/sources/IPool.sol').read_text(encoding='utf8'))
    bytopic={s['topic']:(n,s) for n,s in specs.items()};pool=CONTRACTS['aave_v3'][0]
    transfer=topic('Transfer(address,address,uint256)');swap3=topic('Swap(address,address,int256,int256,uint160,uint128,int24)')
    output=[];evidence=[];trace=[]
    for index,case in enumerate(selected):
        tx=case['borrow_tx'];a=case['account'];receipt=rpc.one('eth_getTransactionReceipt',[tx]);b=int(receipt['blockNumber'],16)
        transfers=[];events=[];swaps=[]
        for l in receipt['logs']:
            t=l['topics'][0] if l['topics'] else '';i=int(l['logIndex'],16)
            if l['address'].lower()==pool and t in bytopic:
                name,s=bytopic[t];d=decode_event(l,s)
                if d.get('onBehalfOf',d.get('user'))==a:events.append((i,name,d))
            if t==transfer and len(l['topics'])==3 and len(words(l['data']))==1:
                transfers.append(dict(idx=i,token=l['address'].lower(),sender=addr(l['topics'][1]),receiver=addr(l['topics'][2]),amount=uint(words(l['data'])[0])))
            if t==swap3:swaps.append((i,l['address'].lower(),[signed(w) for w in words(l['data'])[:2]]))
        status='unresolved';reason='No direct, fully matched same-owner funding path';matched_pool=''
        for i,name,d in events:
            if name!='Borrow' or d.get('user')!=a:continue
            for j,sname,s in events:
                if j<=i or sname!='Supply' or s.get('user')!=a or s['reserve']==d['reserve']:continue
                reborrow=next((x for x in events if x[0]>j and x[1]=='Borrow' and x[2]['reserve']==d['reserve']),None)
                if not reborrow:continue
                for k,p,amounts in swaps:
                    if not i<k<j:continue
                    incoming=[t for t in transfers if t['token']==d['reserve'] and t['sender']==a and t['receiver']==p and i<t['idx']<j]
                    outgoing=[t for t in transfers if t['token']==s['reserve'] and t['sender']==p and t['receiver']==a and i<t['idx']<j]
                    if not incoming or not outgoing:continue
                    qin=sum(t['amount'] for t in incoming);qout=sum(t['amount'] for t in outgoing)
                    if qin!=d['amount'] or qout!=s['amount']:continue
                    # Verify zero opening debt-token balance, including earlier tx in this block.
                    before=uint(call(rpc,d['reserve'],'balanceOf(address)',[a],b-1)[0]);txidx=int(receipt['transactionIndex'],16)
                    logs=rpc.logs(d['reserve'],[transfer],b,b)
                    for l in logs:
                        if int(l['transactionIndex'],16)>=txidx or len(l['topics'])!=3:continue
                        q=uint(words(l['data'])[0])
                        if addr(l['topics'][1])==a:before-=q
                        if addr(l['topics'][2])==a:before+=q
                    if before!=0:reason='Direct matched path, but nonzero opening balance prevents unique funding attribution';continue
                    repaid=sum(x[2]['amount'] for x in events if x[1]=='Repay' and x[2]['reserve']==d['reserve'])
                    borrowed=sum(x[2]['amount'] for x in events if x[1]=='Borrow' and x[2]['reserve']==d['reserve'])
                    if borrowed<=repaid:reason='No positive net debt';continue
                    status='verified_direct_atomic_path';reason='Zero opening loan-token balance; exact borrow→pool swap→supply and same-token reborrow; net debt positive';matched_pool=p
        output.append({'tx':tx,'account':a,'block':b,'status':status,'reason':reason,'matched_pool':matched_pool,'receipt_logs':len(receipt['logs']),
                       'sample_selection':'first 80 unique atomic temporal candidates; not random precision estimate','trace_required_for_unresolved':status=='unresolved'})
        evidence.append({'tx':tx,'transfers':transfers,'protocol_events':events,'swaps':swaps})
        if index<3:
            try:
                tr=rpc.one('debug_traceTransaction',[tx,{'tracer':'callTracer'}]);trace.append({'tx':tx,'available':True});save_json(RUN/'traces'/f'{tx}.json',tr)
            except Exception as e:trace.append({'tx':tx,'available':False,'error':str(e)[:250]})
        if (index+1)%10==0:print(f'C receipt evidence {index+1}/{len(selected)}',flush=True)
        csv_write(OUT/'recursive_receipt_verification.csv',output)
    save_json(RUN/'recursive_receipt_evidence.json',evidence);save_json(RUN/'trace_availability.json',trace)
    if not selected:csv_write(OUT/'recursive_receipt_verification.csv',[],['tx','account','block','status','reason'])

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['labels','flows']);a=p.parse_args()
    if a.phase=='flows':flow_sample()
    else:all_history_labels()
