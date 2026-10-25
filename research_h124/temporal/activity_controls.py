"""Complete-clock activity controls; event availability delayed conservatively.

These are observed event counts, NOT reconstructed outstanding debt or HF stock.
"""
import numpy as np
from .next_common import *
from .h4 import history
from .v2_common import write_npz

def lagged_sum(values,window):
    values=np.asarray(values,float);s=np.r_[0,np.cumsum(values)];i=np.arange(len(values));return s[i]-s[np.maximum(i-window,0)]

def run():
    path=DATA/'h4_prefix_panel_5min.npz'
    with np.load(path) as p:
        mask=p['t']<PRIMARY_END;t=p['t'][mask];y=p['y'][mask]
    if not len(t) or t[-1]+300!=PRIMARY_END:raise ValueError('Base panel does not cover revised primary end')
    start=int(t[0]);end=int(t[-1]+300);size=len(t);names=[];arrays=[];counts={};delay=30
    from .common import connect
    c=connect()
    query="SELECT name,CAST((stamp+?-?)/300 AS INTEGER),count(*) FROM events WHERE protocol='aave_v3' AND name IN ('Borrow','Repay','Supply','Withdraw') AND stamp>=? AND stamp<? GROUP BY name,CAST((stamp+?-?)/300 AS INTEGER)"
    for name,b,n in c.execute(query,(delay,start,start,end,delay,start)):
        if name not in counts:counts[name]=np.zeros(size)
        if 0<=b<size:counts[name][b]=n
    c.close()
    for name in ['Borrow','Repay','Supply','Withdraw']:
        if name not in counts:raise ValueError('Missing complete-clock flow category')
        names.append('log1p_'+name+'_events_prior24h');arrays.append(np.log1p(lagged_sum(counts[name],288)))
    names.append('log_Borrow_Repay_activity_ratio_prior24h');arrays.append(np.log((1+lagged_sum(counts['Borrow'],288))/(1+lagged_sum(counts['Repay'],288))))
    # Separate observed liquidation times (target) from when these become known.
    times=np.array([int(r['stamp'])+delay for r in read(V1_OUT/'h2/episodes.csv') if r['protocol']=='aave_v3'])
    known=np.histogram(times,bins=np.r_[t,end])[0]
    fast=[]
    for half in [.25,2.,168.]:fast.append(np.log1p(history(known,half,1/12)))
    DATA_NEXT.mkdir(parents=True,exist_ok=True);out=DATA_NEXT/'activity_panel.npz'
    write_npz(out,t=t,y=y,X=np.column_stack(arrays),history=np.column_stack(fast),names=np.array(names),history_names=np.array(['known_liquidations_15m','known_liquidations_2h','known_liquidations_7d']))
    result={'updated_utc':now(),'status':'completed_scoped','bins':len(t),'features':names,'source_events':{k:int(v.sum()) for k,v in counts.items()},'availability_delay_seconds':delay,
      'panel_sha256':digest(out),'base_panel_sha256':digest(path),'limitations':['Activity counts are not TVL, risk debt or HF queue','30s availability is a conservative assumption, not actual receipt timestamps','Short/slow liquidation history shifts by availability delay before lagging','Endogenous activity does not establish causal contagion']}
    save(OUT/'activity_readiness.json',result);return result

if __name__=='__main__':print(run(),flush=True)
