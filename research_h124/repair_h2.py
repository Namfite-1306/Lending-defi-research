"""Full-count/native USDC concentration and explicit freshness sensitivities."""
import math,hashlib
from collections import defaultdict
import numpy as np
from .h2 import USDC,WETH,WBTC,normalized
from defi_models.core import concentration
from .repair_common import *

def freshness(age,price,policy,depeg=False):
    if age is None or price is None or not math.isfinite(price) or price<=0 or age<0:return False
    limit={'strict_1h':3600,'six_hours':21600,'one_day':86400,'feed_policy':3600 if depeg else 93600}[policy]
    return age<=limit

def weights(rows,metric):
    out=defaultdict(float)
    for r in rows:
        value=1. if metric=='count' else float(r['debt_raw_upper_estimate'])/1e6 if metric=='USDC_upper' else float(r['debt_raw_lower_bound'])/1e6 if metric=='USDC_lower' else float(r['debt_usd_upper'])
        out[r['borrower']]+=value
    return out

def bootstrap_days(rows,metric,reps=199):
    if not rows:return {'status':'empty_sample','replications':reps}
    days=sorted({r['date'] for r in rows});accounts=sorted({r['borrower'] for r in rows})
    if len(days)<2:return {'status':'insufficient_days','days':len(days),'replications':reps}
    di={d:i for i,d in enumerate(days)};ai={a:i for i,a in enumerate(accounts)};matrix=np.zeros((len(days),len(accounts)))
    for r in rows:matrix[di[r['date']],ai[r['borrower']]]+=1 if metric=='count' else float(r['debt_raw_upper_estimate'])/1e6
    rng=np.random.default_rng(42);values=[]
    for _ in range(reps):
        counts=np.bincount(rng.integers(0,len(days),len(days)),minlength=len(days));w=counts@matrix;w=w[w>0]
        m=normalized(concentration(w),w);values.append([m['hhi_normalized'],m['top1_percent_share']])
    array=np.array(values,dtype=float)
    interval=lambda j:np.quantile(array[np.isfinite(array[:,j]),j],[.025,.975]).tolist() if np.isfinite(array[:,j]).any() else None
    return {'status':'descriptive_day_cluster_bootstrap','days':len(days),'replications':reps,
      'hhi_normalized_95':interval(0),'top1_percent_95':interval(1),
      'scope':'Resamples observed event days; does not include event-free days, owner uncertainty or protocol-level causal inference'}

def run(reps=199):
    out=OUT/'h2';episodes=read(V1_OUT/'h2/episodes.csv');legs=defaultdict(list)
    for r in read(V1_OUT/'h2/collateral_legs.csv'):legs[r['episode']].append(r)
    # All alert state uses only prior-block quotes; never infer depeg from future prices.
    raw=sorted((r for r in read(SOURCE/'processed/chainlink_price_updates.csv') if r['feed']=='USDC/USD'),key=lambda r:int(r['block']))
    alerts=[(int(r['block']),int(r['stamp'])) for r in raw if abs(float(r['price_usd'])-1)>.005]
    import bisect
    alert_blocks=[r[0] for r in alerts]
    for r in episodes:
        r['debt_price_age_seconds']=float(r['debt_price_age_seconds']) if r['debt_price_age_seconds'] else None
        r['debt_usd_upper']=float(r['debt_usd_upper']) if r['debt_usd_upper'] else None
        j=bisect.bisect_left(alert_blocks,int(r['block']))-1
        r['known_depeg']=j>=0 and 0<=int(r['stamp'])-alerts[j][1]<=86400
    rows=[];coverage=[];ci=[]
    for window,lo,hi in [('common_calendar_2024','2024-02-01','2025-01-01'),('common_extended','2024-02-01','2026-10-01')]:
      for token in [WETH,WBTC]:
       for protocol in ['aave_v3','compound_v3_usdc','morpho_blue']:
        sample=[r for r in episodes if r['protocol']==protocol and lo<=r['date']<hi and r['debt_token']==USDC and len(legs[r['episode']])==1 and legs[r['episode']][0]['token']==token]
        groups=[('no_USD_price_filter','count',sample),('no_USD_price_filter','USDC_upper',sample),('no_USD_price_filter','USDC_lower',[r for r in sample if r.get('debt_raw_lower_bound') not in ['',None]])]
        for policy in ['strict_1h','six_hours','one_day','feed_policy']:
            good=[]
            for r in sample:
                p=(r['debt_usd_upper']/(float(r['debt_raw_upper_estimate'])/1e6)) if r['debt_usd_upper'] is not None and int(r['debt_raw_upper_estimate'])>0 else None
                if freshness(r['debt_price_age_seconds'],p,policy,r['known_depeg']):good.append(r)
            groups.extend([(policy,'count',good),(policy,'USD',good)])
            coverage.append({'window':window,'token':token,'protocol':protocol,'policy':policy,'matched_events':len(sample),'kept_events':len(good),'event_coverage':len(good)/len(sample) if sample else None,
              'known_depeg_events':sum(r['known_depeg'] for r in sample),'definition':'26h normal, 1h for known prior-24h depeg alert' if policy=='feed_policy' else policy})
        for policy,metric,good in groups:
            w=weights(good,metric);ranked=sorted(w,key=lambda a:(-w[a],a));N=len(ranked)
            for drop,n in [('none',0),('top1',1),('top5',5),('top10',10),('top1percent',max(1,math.ceil(N*.01)))]:
                kept=ranked[n:];v=[w[a] for a in kept]
                rows.append({'window':window,'token':token,'protocol':protocol,'policy':policy,'metric':metric,'drop':drop,'events_before_drop':len(good),'matched_events':len(sample),'wallets_removed':min(n,N),
                  'ranking':metric+'-ranked ex-post influence sensitivity','retained_wallets_sha256':hashlib.sha256('\n'.join(sorted(kept)).encode()).hexdigest(),**normalized(concentration(v),v)})
            if policy=='no_USD_price_filter' and metric in ['count','USDC_upper']:
                ci.append({'window':window,'token':token,'protocol':protocol,'metric':metric,**bootstrap_days(good,metric,reps)})
    write(out/'concentration.csv',rows);write(out/'coverage.csv',coverage);save(out/'uncertainty.json',ci)
    result={'updated_utc':now(),'status':'completed_scoped','rows':len(rows),'coverage_rows':len(coverage),'bootstrap_replications':reps,
      'source_hashes':{n:digest(V1_OUT/'h2'/n) for n in ['episodes.csv','collateral_legs.csv']},
      'price_policy':{'USDC_normal_seconds':93600,'known_depeg_seconds':3600,'depeg_deviation':.005,'known_alert_lookback_seconds':86400,'classification':'assumed sensitivity policy, not verified feed SLA'},
      'limitations':['Native USDC is a token unit, not assumed USD parity','Full counts and USD counts have different supports; label explicitly',
        'Last-known oracle cannot identify unobserved depeg between updates; independent market prices still missing',
        'Exactly one WETH/WBTC collateral and USDC debt only; small Morpho samples remain','Debt absorption/repayment semantics and owner uncertainty remain']}
    save(out/'summary.json',result);return result

if __name__=='__main__':print(run())
