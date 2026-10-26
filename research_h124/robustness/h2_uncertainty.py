"""Paired calendar-day bootstrap of the NEW market-price sample.

Includes event-free calendar days. Moving-block (7-day) sensitivity retains short
serial dependence. Intervals are descriptive, not protocol design causal effects.
"""
import argparse,math
from collections import defaultdict
from datetime import date
import numpy as np
from scipy.sparse import csr_matrix
from defi_models.core import concentration
from research_h124.h2 import normalized
from .common import *

TOKENS=['0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2','0x2260fac5e5542a773aa44fbcfedf7c193bc2c599']
PROTOCOLS=['aave_v3','compound_v3_usdc','morpho_blue']

def calendar_counts(days,reps,block,seed=42):
    rng=np.random.default_rng(seed);result=np.zeros((reps,days),dtype=np.int32)
    for k in range(reps):
        starts=rng.integers(0,days,math.ceil(days/block))
        draw=((starts[:,None]+np.arange(block))%days).ravel()[:days]
        result[k]=np.bincount(draw,minlength=days)
    return result

def metrics(values):
    return normalized(concentration(values),values)

def sample_bootstrap(rows,metric,lo,days,counts):
    accounts=sorted({r['borrower'] for r in rows});ai={a:i for i,a in enumerate(accounts)}
    if not accounts:return None
    ii=np.array([(date.fromisoformat(r['date'])-lo).days for r in rows]);jj=np.array([ai[r['borrower']] for r in rows])
    values=np.array([1. if metric=='count' else float(r['debt_native_USDC']) if metric=='native_USDC' else float(r['market_debt_usd']) for r in rows])
    if not np.isfinite(values).all() or (values<0).any():raise ValueError('Invalid concentration weights')
    weights=csr_matrix((values,(ii,jj)),shape=(days,len(accounts)))
    presence=csr_matrix((np.ones(len(rows)),(ii,jj)),shape=weights.shape)
    sums=np.asarray(weights.sum(axis=0)).ravel();point=metrics(sums)
    sampled=(weights.T@counts.T).T;seen=(presence.T@counts.T).T>0
    draw=[]
    for w,mask in zip(sampled,seen):
        m=metrics(w[mask]);draw.append([m['hhi_normalized'] if m['hhi_normalized'] is not None else np.nan,m['top1_percent_share'] if m['top1_percent_share'] is not None else np.nan])
    return point,np.array(draw),sums

def run(reps=999):
    if not 99<=reps<=10000:raise ValueError('Replication count out of range')
    path=OLD/'market_event_quotes.csv';events=read(path);source_hash=digest(path)
    rows=[];differences=[];influence=[]
    for window,start,end in [('calendar_2024','2024-02-01','2025-01-01'),('primary_extended','2024-02-01','2026-04-01')]:
        lo=date.fromisoformat(start);days=(date.fromisoformat(end)-lo).days
        draws={block:calendar_counts(days,reps,block) for block in [1,7]}
        for token in TOKENS:
          for age in [60,300,3600]:
            for metric in ['count','native_USDC','market_USD']:
              paired={}
              for protocol in PROTOCOLS:
                sample=[r for r in events if r['protocol']==protocol and r['collateral_token']==token and start<=r['date']<end and r['market_debt_usd']!='' and r['coverage_verified']=='True' and 0<=float(r['market_age_seconds'])<=age]
                common={'window':window,'token':token,'support':'market_fresh','max_age_seconds':age,'metric':metric,'protocol':protocol}
                for block,counts in draws.items():
                    result=sample_bootstrap(sample,metric,lo,days,counts)
                    if result is None:rows.append({**common,'block_days':block,'status':'empty_sample'});continue
                    point,values,weights=result;valid=np.isfinite(values).all(axis=1)
                    status='small_sample_no_interval' if point['entities']<30 else 'completed_descriptive' if valid.mean()>=.95 else 'insufficient_bootstrap_support'
                    row={**common,'block_days':block,'status':status,'calendar_days':days,'event_days':len({r['date'] for r in sample}),'replications':reps,'valid_replications':int(valid.sum()),'zero_or_degenerate_replications':int((~valid).sum()),'entities':point['entities'],'events':len(sample),'hhi_normalized':point['hhi_normalized'],'top1_percent_share':point['top1_percent_share']}
                    if status=='completed_descriptive':
                        for j,label in enumerate(['hhi','top1_percent']):
                            a,b=np.quantile(values[valid,j],[.025,.975]);row[label+'_lower']=float(a);row[label+'_upper']=float(b)
                        paired[protocol,block]=(point,values)
                    rows.append(row)
                    if block==1:
                        ranking=np.argsort(-weights,kind='stable')
                        for drop,n in [('largest_wallet',1),('top_1_percent_wallets',max(1,math.ceil(len(weights)*.01)))]:
                            m=metrics(weights[ranking[n:]])
                            influence.append({**common,'drop':drop,'removed_wallets':n,**{k:m[k] for k in ['entities','hhi_normalized','top1_percent_share']}})
              for block in [1,7]:
                if ('aave_v3',block) in paired and ('compound_v3_usdc',block) in paired:
                    a,av=paired['aave_v3',block];b,bv=paired['compound_v3_usdc',block];valid=np.isfinite(av[:,0])&np.isfinite(bv[:,0]);delta=bv[valid,0]-av[valid,0]
                    lower,upper=np.quantile(delta,[.025,.975])
                    differences.append({'window':window,'token':token,'support':'market_fresh','max_age_seconds':age,'metric':metric,'block_days':block,'comparison':'Compound minus Aave normalized HHI','point_difference':b['hhi_normalized']-a['hhi_normalized'],'lower':float(lower),'upper':float(upper),'paired_calendar_replications':int(valid.sum()),'status':'descriptive_paired_interval_not_causal_test'})
        write(OUT/'h2/intervals.csv',rows);write(OUT/'h2/paired_differences.csv',differences);write(OUT/'h2/influence.csv',influence)
        print('H2 UNCERTAINTY',window,len(rows),flush=True)
    if digest(path)!=source_hash:raise ValueError('Source changed during bootstrap')
    result={'updated_utc':now(),'status':'completed_descriptive','replications':reps,'seed':42,'block_lengths_days':[1,7],'paired_across_protocols':True,'calendar_includes_event_free_days':True,'source_sha256':source_hash,'interval_rows':len(rows),'small_sample_intervals_suppressed':True,
      'limitations':['Historical calendar resampling assumes exchangeable day clusters or stationary circular 7-day blocks','Intervals do not resolve owner/address identity or debt-concept differences','Only market_fresh support; no borrowing intervals from older or oracle-common samples','Day/block bootstrap intervals are not proof of a causal protocol-design effect']}
    save(OUT/'h2/summary.json',result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--replications',type=int,default=999);a=p.parse_args();run(a.replications)
