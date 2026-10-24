"""Episode/leg reconstruction, Comet credit correction and matched concentration.

No many-to-many joins; missing prices remain missing. Comet debt is explicitly
bounded for principal rounding, not relabelled basePaidOut. Absorber is not payer.
"""
import argparse,json,math,bisect,hashlib
from collections import defaultdict,Counter
from pathlib import Path
from decimal import Decimal as D
import numpy as np
from defi_models.core import Data,DEFAULTS,concentration
from defi_data.pipeline import CONTRACTS,call_request
from defi_data.evm import words,uint
from defi_data.rpc import Rpc
from .common import SOURCE,DATA,OUT,read,write,save,connect,digest,now

USDC='0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'
WETH='0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'
WBTC='0x2260fac5e5542a773aa44fbcfedf7c193bc2c599'
ZERO='0x'+'0'*40


def link_comet(events):
    groups=defaultdict(list);episodes=[];legs=[]
    for r in events:groups[r['tx']].append(r)
    for tx,rs in groups.items():
        rs.sort(key=lambda r:r['idx']);pending=defaultdict(list)
        for i,r in enumerate(rs):
            d=r['decoded'];borrower=d.get('borrower')
            if r['name']=='AbsorbCollateral':pending[borrower].append(r)
            if r['name']!='AbsorbDebt':continue
            key=f'{tx}:{r["idx"]}';credit=0;credit_log=None
            # Comet emits the supply-credit mint immediately after AbsorbDebt;
            # inspect only the next selected log, not any later mint in the tx.
            if i+1<len(rs):
                nxt=rs[i+1];nd=nxt['decoded']
                if nxt['idx']==r['idx']+1 and nxt['name']=='Transfer' and nd.get('from')==ZERO and nd.get('to')==borrower:
                    credit=int(nd['amount']);credit_log=nxt['idx']
                elif nxt['name']=='Transfer' and nd.get('from')==ZERO and nd.get('to')==borrower:
                    raise ValueError('Nonadjacent borrower credit mint requires trace; not normalized silently')
            paid=int(d['basePaidOut']);estimate=paid-credit
            if estimate<0:raise ValueError('Comet supply credit exceeds payout')
            local=pending.pop(borrower,[])
            for leg in local:
                ld=leg['decoded'];legs.append(dict(episode=key,protocol='compound_v3_usdc',block=r['block'],stamp=r['stamp'],borrower=borrower,
                  token=ld['asset'],amount_raw=str(ld['collateralAbsorbed']),oracle_reported_usd=str(D(ld['usdValue'])/10**8),logidx=leg['idx']))
            episodes.append(dict(episode=key,protocol='compound_v3_usdc',tx=tx,logidx=r['idx'],transaction_index=r.get('txidx'),block=r['block'],stamp=r['stamp'],borrower=borrower,
              debt_token=USDC,debt_raw_upper_estimate=str(estimate),base_paid_out_raw=str(paid),supply_credit_raw=str(credit),credit_log=credit_log,
              collateral_legs=len(local),collateral_tokens='|'.join(sorted({x['decoded']['asset'] for x in local})),
              normalization='credit_corrected_upper_estimate_rounding_not_yet_bounded',measurement='debt absorbed by protocol, not liquidator cash repayment',
              oracle_base_paid_out_usd=str(D(d['usdValue'])/10**8)))
        if any(pending.values()):raise ValueError('Unmatched AbsorbCollateral logs remain in transaction')
    return episodes,legs


class Prices:
    def __init__(self,rows):
        groups=defaultdict(list)
        for r in rows:groups[r['feed']].append((int(r['block']),int(r['stamp']),float(r['price_usd'])))
        self.feeds={}
        for feed,values in groups.items():
            values.sort();self.feeds[feed]=([v[0] for v in values],values)
    def get(self,token,block,stamp):
        feed={USDC:'USDC/USD',WETH:'ETH/USD',WBTC:'BTC/USD','0xdac17f958d2ee523a2206206994597c13d831ec7':'USDT/USD','0x6b175474e89094c44da98b954eedeac495271d0f':'DAI/USD'}.get(token)
        if feed not in self.feeds:return None,None,'missing_feed'
        blocks,values=self.feeds[feed];j=bisect.bisect_left(blocks,block)-1
        if j<0:return None,None,'missing_prior_block_price'
        b,at,p=values[j];age=stamp-at
        if age<0 or not math.isfinite(p) or p<=0:return None,None,'invalid_price'
        return p,age,'BTC_proxy_basis_unmeasured' if token==WBTC else 'Chainlink_prior_block_last_known'


def bounded_comet(episodes,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);rpc=Rpc(out/'rpc',batch_size=50,multicall=True,timeout=12,retry_attempts=1)
    market=CONTRACTS['compound_v3_usdc'][0];blocks=sorted({int(r['block']) for r in episodes})
    scale=uint(words(rpc.one(*call_request(market,'baseIndexScale()',[],blocks[-1])))[0]);indices={};errors=[]
    for start in range(0,len(blocks),50):
        group=blocks[start:start+50]
        answers=rpc.many([call_request(market,'totalsBasic()',[],b) for b in group],allow_errors=True)
        for b,raw in zip(group,answers):
            if isinstance(raw,dict):errors.append({'block':b,'stage':'supply_index'});continue
            w=words(raw)
            if len(w)!=8:raise ValueError('Unsupported Comet totalsBasic ABI')
            indices[b]=uint(w[0])
    for r in episodes:
        if r['block'] not in indices:continue
        # floor(principalValueSupply) then floor(presentValueSupply): a safe
        # interval allowing two rounding operations, using end-block index upper
        # bound. Interest indices nondecreasing in the verified Comet design.
        quantum=(indices[r['block']]+scale-1)//scale+1;upper=int(r['debt_raw_upper_estimate'])
        r.update(debt_raw_lower_bound=str(max(0,upper-quantum)),rounding_bound_raw=str(quantum),
          normalization='credit_corrected_rounding_interval; implementation_semantics_assumed_from_archived_source')
    save(out/'normalization_provenance.json',{'collected_utc':now(),'blocks':len(indices),'base_index_scale':scale,'errors':errors,
      'source_hash':digest(SOURCE/'CometWithExtendedAssetList.sol'),'limitations':['Archived implementation semantics not proven bytecode-equivalent at every historical upgrade',
        'Debt interval, not exact intra-transaction reconstruction','Absorbed debt is not cash repaid by an external liquidator']})
    return episodes


def normalized(metrics,values=None):
    n=metrics['entities'];h=metrics['hhi'];g=metrics['gini']
    weights=sorted(list(values)) if values is not None else []
    return dict(metrics,hhi_normalized=(h-1/n)/(1-1/n) if n>1 and h is not None else None,
      gini_finite_n_normalized=g*n/(n-1) if n>1 and g is not None else None,effective_entity_fraction=1/(h*n) if h and n else None,
      top1_percent_share=sum(weights[-max(1,math.ceil(n*.01)):])/sum(weights) if weights and sum(weights)>0 else None,small_entity_count=n<30)


def sensitivity(episodes,legs):
    by_episode=defaultdict(list)
    for r in legs:by_episode[r['episode']].append(r)
    output=[];coverage=[]
    for window,lo,hi in [('common_calendar_2024','2024-02-01','2025-01-01'),('common_extended','2024-02-01','2026-10-01')]:
      for token in [WETH,WBTC]:
       for protocol in ['aave_v3','compound_v3_usdc','morpho_blue']:
        sample=[r for r in episodes if r['protocol']==protocol and lo<=r['date']<hi and r['debt_token']==USDC and len(by_episode[r['episode']])==1 and by_episode[r['episode']][0]['token']==token and (protocol!='compound_v3_usdc' or r.get('debt_raw_lower_bound') is not None)]
        for max_age in [900,3600,21600,86400]:
            good=[r for r in sample if r['debt_price_age_seconds'] is not None and r['debt_price_age_seconds']<=max_age and r['debt_usd_upper'] is not None]
            coverage.append(dict(window=window,token=token,protocol=protocol,max_price_age=max_age,matched_episodes=len(sample),priced_episodes=len(good),event_price_coverage=len(good)/len(sample) if sample else None,
              unit='single-collateral USDC-debt episode; Comet interval, Aave event debt, Morpho repaid+badDebt'))
            reference_weights=defaultdict(float)
            for r in good:reference_weights[r['borrower']]+=r['debt_usd_upper']
            reference_ranking=sorted(reference_weights,key=lambda a:(-reference_weights[a],a))
            for metric in ['count','usd']:
                weights=defaultdict(float)
                for r in good:weights[r['borrower']]+=1 if metric=='count' else r['debt_usd_upper']
                ranked=reference_ranking
                drops=[('none',0),('top1',1),('top5',5),('top10',10),('top1percent',max(1,math.ceil(len(ranked)*.01)))]
                for label,number in drops:
                    retained=ranked[number:];values=[weights[a] for a in retained]
                    output.append(dict(window=window,token=token,protocol=protocol,max_price_age=max_age,metric=metric,drop=label,
                      wallets_removed=min(number,len(ranked)),selection='USD-ranked ex_post_influence_sensitivity_not_causal',
                      retained_wallets_sha256=hashlib.sha256('\n'.join(sorted(retained)).encode()).hexdigest(),common_priced_sample=True,**normalized(concentration(values),values)))
            # Explicit lower/upper debt interval sensitivity on identical support.
            lower=defaultdict(float)
            for r in good:lower[r['borrower']]+=r['debt_usd_lower'] if r['debt_usd_lower'] is not None else r['debt_usd_upper']
            output.append(dict(window=window,token=token,protocol=protocol,max_price_age=max_age,metric='usd_lower_rounding_bound',drop='none',wallets_removed=0,selection='same sample',common_priced_sample=True,**normalized(concentration(lower.values()),lower.values())))
    return output,coverage


def run(source=SOURCE,out=OUT/'h2',network=True):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);data=Data(source,DEFAULTS)
    meta={r['token']:r for r in data.read('token_registry.csv')};registry={r['market_id']:r for r in data.read('morpho_market_registry_full.csv')}
    prices=Prices(data.read('chainlink_price_updates.csv'));c=connect(source);c.row_factory=__import__('sqlite3').Row
    reference=data.read('liquidations_model_table.csv')
    comet=[]
    for raw in c.execute("SELECT block,txidx,idx,tx,stamp,name,decoded FROM events WHERE protocol='compound_v3_usdc' AND tx IN (SELECT tx FROM events WHERE protocol='compound_v3_usdc' AND name='AbsorbDebt') ORDER BY block,txidx,idx"):
        r=dict(raw);r['decoded']=json.loads(r['decoded']);comet.append(r)
    episodes,legs=link_comet(comet)
    if network:episodes=bounded_comet(episodes,DATA/'h2')
    for proto,name in [('aave_v3','LiquidationCall'),('morpho_blue','Liquidate')]:
        for raw in c.execute('SELECT block,txidx,idx,tx,stamp,decoded FROM events WHERE protocol=? AND name=? ORDER BY block,txidx,idx',(proto,name)):
            r=dict(raw);d=json.loads(r['decoded']);key=f'{r["tx"]}:{r["idx"]}'
            if proto=='aave_v3':borrower=d['user'];debt_token=d['debtAsset'];collateral=d['collateralAsset'];debt=int(d['debtToCover']);seized=d['liquidatedCollateralAmount'];bad=0
            else:
                market=registry[d['id']];borrower=d['borrower'];debt_token=market['loan_token'];collateral=market['collateral_token'];bad=int(d['badDebtAssets']);debt=int(d['repaidAssets'])+bad;seized=d['seizedAssets']
            episodes.append(dict(episode=key,protocol=proto,tx=r['tx'],logidx=r['idx'],block=r['block'],stamp=r['stamp'],borrower=borrower,debt_token=debt_token,
              debt_raw_upper_estimate=str(debt),debt_raw_lower_bound=str(debt),bad_debt_raw=str(bad),collateral_legs=1,collateral_tokens=collateral,
              normalization='reported_liquidation_debt; Aave extra deficit writeoffs unobserved' if proto=='aave_v3' else 'repaidAssets_plus_badDebtAssets',
              measurement='event-reported borrower debt addressed; financing mechanism differs'))
            legs.append(dict(episode=key,protocol=proto,block=r['block'],stamp=r['stamp'],borrower=borrower,token=collateral,amount_raw=str(seized),
              measurement='event-reported collateral; Aave may exclude protocol fee, not gross-comparable',logidx=r['idx']))
    c.close()
    expected={f'{r["tx"]}:{r["logidx"]}' for r in reference}
    if len(episodes)!=len(expected) or {r['episode'] for r in episodes}!=expected:raise ValueError('Raw event episodes differ from frozen liquidation universe')
    for r in episodes:
        r['date']=__import__('datetime').datetime.fromtimestamp(r['stamp'],__import__('datetime').timezone.utc).date().isoformat()
        token=r['debt_token'];price,age,method=prices.get(token,r['block'],r['stamp']);decimals=int(meta[token]['decimals']) if token in meta else None
        r.update(debt_price_age_seconds=age,debt_price_method=method,debt_usd_upper=float(D(r['debt_raw_upper_estimate'])/10**decimals)*price if decimals is not None and price is not None else None,
          debt_usd_lower=float(D(r['debt_raw_lower_bound'])/10**decimals)*price if decimals is not None and price is not None and r.get('debt_raw_lower_bound') is not None else None)
    for r in legs:
        p,age,method=prices.get(r['token'],r['block'],r['stamp']);m=meta.get(r['token'])
        r.update(price_age_seconds=age,price_method=method,collateral_reported_usd=float(D(r['amount_raw'])/10**int(m['decimals']))*p if m and p else None)
    table,coverage=sensitivity(episodes,legs);write(out/'episodes.csv',episodes);write(out/'collateral_legs.csv',legs)
    write(out/'matched_concentration_sensitivity.csv',table);write(out/'matched_coverage.csv',coverage)
    com=[r for r in episodes if r['protocol']=='compound_v3_usdc'];missing=sum(not r['collateral_legs'] for r in com)
    summary={'status':'completed_scoped_with_semantic_limits','generated_utc':now(),'episodes':len(episodes),'comet_episodes':len(com),'comet_collateral_legs':sum(r['protocol']=='compound_v3_usdc' for r in legs),
      'comet_missing_collateral_episodes':missing,'comet_credit_corrections':sum(int(r['supply_credit_raw'])>0 for r in com),'comet_rounding_bounded':sum('debt_raw_lower_bound' in r for r in com),
      'sensitivity_rows':len(table),'primary_scope':'2024-02-01 to 2025-01-01; USDC debt, exactly one collateral token, exact WETH/WBTC address',
      'limitations':['Cross-protocol financing differs: Comet protocol absorption versus Aave repayment; do not label all as liquidator repayment',
        'Comet credit correction has principal-rounding interval and assumes archived implementation semantics, not all-upgrade trace verification',
        'Aave event debt excludes unobserved extra deficit writeoffs, particularly relevant for extended newer-period comparison',
        'Aave collateral event may be net of protocol fee, so no pooled gross-collateral-USD ranking is claimed',
        'Prior-block Chainlink value, no within-block future quote; WBTC uses BTC proxy with unmeasured basis',
        'Large-wallet exclusions are ex-post influence checks; addresses are not identified beneficial owners','N=1 normalized HHI/Gini undefined; NA not zero'],
      'inputs':{str(p.relative_to(source)):digest(p) for p in sorted(data.used)}}
    save(out/'summary.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2));return summary

def main():
    p=argparse.ArgumentParser();p.add_argument('--offline',action='store_true');a=p.parse_args();run(network=not a.offline)
if __name__=='__main__':main()
