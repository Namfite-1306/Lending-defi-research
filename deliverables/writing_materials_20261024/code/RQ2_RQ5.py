"""RQ2 concentration and RQ5 sampled cross-protocol exposure network.

Shared production implementations. Run: python -m defi_models.rq2_rq5 --help
"""
import sys
from pathlib import Path
if __package__ in (None, ''):
    # Place this file anywhere inside the repository; locate shared audited code.
    _root = next((p for p in Path(__file__).resolve().parents if (p/'defi_models/core.py').is_file()), None)
    if _root is None:
        raise SystemExit('Place this file inside Lending-defi-research, which must contain defi_models/. See HUONG_DAN_CHAY.md.')
    sys.path.insert(0, str(_root))
    __package__ = 'defi_models'
import math
from collections import Counter, defaultdict
from .core import write_csv, require, concentration, summary

def rq2(data,out,cfg):
    events=data.read('liquidations_model_table.csv');groups=defaultdict(lambda:defaultdict(float));coverage=Counter()
    for r in events:
        proto=r['protocol'];year=r['timestamp_utc'][:4];priced=bool(r['reported_event_amount_market_usd'])
        if priced:
            require(math.isfinite(float(r['reported_event_amount_market_usd'])) and float(r['reported_event_amount_market_usd'])>=0,'Invalid liquidation valuation')
            age=float(r['price_age_seconds']);limit=7200 if r['debt_token']=='0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2' else 90000
            require(math.isfinite(age) and 0<=age<=limit and r['valuation_status']=='market_price_last_known','Priced liquidation has stale/future/unverified valuation')
        coverage[proto,'events']+=1;coverage[proto,'priced']+=priced
        for period in ('all',year):
            for dim,key in [('borrower',r['borrower']),('debt_token',r['debt_token']),('collateral_token',r['collateral_token'])]:
                # Unknown identities are an explicit missing bucket, not silently dropped.
                groups[proto,period,dim,'event_count'][key or 'UNKNOWN']+=1
                if priced:groups[proto,period,dim,'reported_amount_market_usd_priced_subset'][key or 'UNKNOWN']+=float(r['reported_event_amount_market_usd'])
    metrics=[];top=[]
    for (proto,period,dim,measure),weights in sorted(groups.items()):
        metrics.append(dict(protocol=proto,period=period,dimension=dim,measure=measure,**concentration(weights.values())))
        total=sum(weights.values())
        for rank,(entity,v) in enumerate(sorted(weights.items(),key=lambda x:x[1],reverse=True)[:20],1):
            top.append(dict(protocol=proto,period=period,dimension=dim,measure=measure,rank=rank,entity=entity,value=v,share=v/total if total else None))
    write_csv(out/'concentration.csv',metrics);write_csv(out/'top_entities.csv',top)
    cov=[dict(protocol=p,events=coverage[p,'events'],priced_events=coverage[p,'priced'],priced_fraction=coverage[p,'priced']/coverage[p,'events']) for p in sorted({r['protocol'] for r in events})]
    write_csv(out/'valuation_coverage.csv',cov)
    return summary('ready_scoped','HHI, Gini and top shares by protocol and year',
      ['USD measures use priced subset, not full population','Comet basePaidOut is not equivalent to Aave repaid debt; protocols are never pooled',
       'Event counts count liquidation logs, not unique loans'],coverage=cov)

def rq5(data,out,cfg):
    ps=data.read('exposures_valued_sample.csv');blocks={r['block'] for r in ps};require(len(blocks)==1,'Exposure network must use synchronized block')
    edges=[];debts=defaultdict(lambda:defaultdict(float));collateral=defaultdict(lambda:defaultdict(float));unknown=0;seen=set()
    for r in ps:
        key=tuple(r[k] for k in ['protocol','account','market_id','asset','kind'])
        require(key not in seen,'Duplicate exposure would double-count network weight');seen.add(key)
        if r['priced']!='True':unknown+=1;continue
        value=float(r['value_usd']);kind=r['kind'];protocol=r['protocol'];account=r['account']
        require(math.isfinite(value) and value>=0,'Invalid valued exposure')
        edges.append(dict(wallet=account,protocol=protocol,market=r['market_id'],asset=r['asset'],kind=kind,value_usd=value,block=r['block'],causal_claim=False))
        if kind=='debt':debts[account][protocol]+=value
        if kind=='collateral':collateral[account][protocol]+=value
    write_csv(out/'valued_edges.csv',edges)
    require(edges,'No priced exposure available; cannot interpret empty network as no contagion')
    protocols=sorted({r['protocol'] for r in ps});overlap=[]
    for a in protocols:
        for b in protocols:
            if a>=b:continue
            shared=[w for w,d in debts.items() if d.get(a,0)>0 and d.get(b,0)>0]
            overlap.append(dict(protocol_a=a,protocol_b=b,shared_debt_wallets=len(shared),minimum_shared_debt_usd=sum(min(debts[w][a],debts[w][b]) for w in shared),edge_type='common_wallet_overlap_not_interprotocol_claim'))
    write_csv(out/'protocol_overlap.csv',overlap)
    # Accounting sensitivity: a protocol shock marks sampled borrowers distressed,
    # then measures their other sampled debts. No invented default propagation rates.
    scenarios=[]
    for origin in protocols:
        wallets={w for w,d in debts.items() if d.get(origin,0)>0}
        for target in protocols:
            if origin==target:continue
            scenarios.append(dict(origin=origin,target=target,affected_common_wallets=sum(debts[w].get(target,0)>0 for w in wallets),
              coexposed_debt_usd=sum(debts[w].get(target,0) for w in wallets),interpretation='upper-bound shared-wallet exposure screen; not realized losses'))
    write_csv(out/'common_wallet_sensitivity.csv',scenarios)
    return summary('exploratory','Sampled multilayer exposure network and common-wallet exposure sensitivity',
      ['Activity-selected sample, not full-market network','Co-exposure is not a direct protocol claim or causal contagion channel',
       'No invented recovery rate, default rule or contagion coefficient; propagation estimation requires additional identification'],
       block=next(iter(blocks)),valued_edges=len(edges),unpriced_rows=unknown,wallets=len({r['account'] for r in ps}),protocols=protocols)

def main(argv=None):
    from . import __main__ as _runner
    _runner.MODELS.update({2: rq2, 5: rq5})
    from .member_cli import run_member
    return run_member([2, 5], argv)


if __name__ == "__main__":
    raise SystemExit(main())
