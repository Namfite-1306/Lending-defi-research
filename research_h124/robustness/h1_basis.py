"""Quarterly measured DEX repricing and explicitly assumed derivative haircuts.

Both collateral and debt are repriced. Historical LT/revision integer HF rules
are reused. No basis values are interpolated into an artificial minute series.
"""
import copy
import numpy as np
from defi_models.core import Portfolio,DEFAULTS
from .common import *

def reprice(portfolio,factors):
    f=np.asarray(factors,float)
    if f.shape!=(len(portfolio.tokens),) or not np.isfinite(f).all() or (f<=0).any():raise ValueError('Invalid token price factors')
    q=copy.copy(portfolio);q.c=portfolio.c*f;q.d=portfolio.d*f;q.repay=portfolio.repay*f
    return q

def run():
    root=ROOT/'data/research_h124_20261024/h1'
    basis_file=ROOT/'results/research_h124_v2_20261024/h4_quarterly_basis.csv'
    basis=read(basis_file);rows=[];audits=[];sources={str(basis_file.relative_to(ROOT)):digest(basis_file)}
    published=read(ROOT/'results/research_h124_20261024/h1/stress_curves.csv')
    plan=[r for r in load(root/'quarter_plan.json') if r['cutoff_exclusive_utc']<=PRIMARY_END]
    if len(plan)!=13:raise ValueError('Expected exactly 13 approved quarters')
    for item in plan:
        folder=root/item['quarter'];scope=load(folder/'scope.json');freeze=load(folder/'freeze_manifest.json')
        if not scope.get('full_snapshot_complete') or not scope.get('model_hf_passed') or not scope.get('aggregate_debt_passed'):raise ValueError('Incomplete validated quarter')
        for rel,h in freeze['files'].items():
            if digest(folder/rel)!=h:raise ValueError('Frozen snapshot changed')
            sources[str((folder/rel).relative_to(ROOT))]=h
        records=read(folder/'positions.csv');p=Portfolio(records,DEFAULTS);checks=sorted(read(folder/'validation.csv'),key=lambda r:r['account'])
        hf,_=p.stress();expected=np.array([float(r['hf_reported']) for r in checks])
        if len(p.accounts)!=scope['active_debt_wallets'] or [r['account'] for r in checks]!=p.accounts or not np.all(np.abs(hf-expected)/np.maximum(abs(expected),1e-12)<=1e-4):raise ValueError('HF/borrower coverage mismatch')
        prices={r['symbol']:float(r['price_usd']) for r in records};observed=np.ones(len(p.tokens));measured=[]
        for b in basis:
            if b['quarter']!=item['quarter'] or b['status']!='observed_quarter_spot' or b['symbol'] not in p.symbols:continue
            if int(b['block'])!=int(scope['block']):raise ValueError('Basis/snapshot block mismatch')
            symbol=b['symbol'];ratio=float(b['weth_per_token'])*prices['WETH']/prices[symbol]
            observed[p.symbols.index(symbol)]=ratio;measured.append(symbol)
        derivative=p.eth&np.array([s!='WETH' for s in p.symbols])
        cases=[('oracle_factor_baseline',np.ones(len(p.tokens)),'canonical oracle valuations'),('same_block_DEX_wstETH_WBTC',observed,'same-block measured DEX spot; sparse pairs only')]
        for haircut in [.02,.05,.1]:cases.append(('assumed_derivative_basis_'+str(int(haircut*100))+'pct',np.where(derivative,1-haircut,1.),'assumed sensitivity, not fitted or observed basis'))
        canonical=None
        for name,f,meaning in cases:
            portfolio=reprice(p,f);base_hf,_=portfolio.stress();h,d=portfolio.stress(.2,.2);eligible=(h<1)&(d>0)
            share=float(d[eligible].sum()/d.sum());row={'quarter':item['quarter'],'block':scope['block'],'case':name,'shock':.2,'mapping':'factor_family_1to1','eligible_debt_share':share,'eligible_debt_usd':float(d[eligible].sum()),'total_debt_usd':float(d.sum()),'eligible_wallets':int(eligible.sum()),'newly_eligible_wallets':int((eligible&(base_hf>=1)).sum()),'measured_symbols':','.join(measured) if name=='same_block_DEX_wstETH_WBTC' else '', 'interpretation':meaning}
            if name=='oracle_factor_baseline':
                canonical=share;ref=next(r for r in published if r['quarter']==item['quarter'] and r['mapping']=='factor_family_1to1' and r['scenario']=='joint' and abs(float(r['shock'])-.2)<1e-9)
                if not np.isclose(share,float(ref['eligible_debt_share']),rtol=1e-10,atol=1e-12):raise ValueError('Zero-basis model differs from frozen H1')
            row['change_vs_canonical_pp']=(share-canonical)*100;rows.append(row)
        audits.append({'quarter':item['quarter'],'full_snapshot_verified':True,'HF_reconciled':True,'aggregate_debt_verified':True,'same_block_basis_symbols':','.join(measured),'baseline_matches_frozen_curve':True})
        write(OUT/'h1/basis_stress.csv',rows);write(OUT/'h1/audit.csv',audits);print('H1 BASIS',item['quarter'],','.join(measured),flush=True)
    if any(digest(ROOT/p)!=h for p,h in sources.items()):raise ValueError('Input changed during H1 audit')
    result={'updated_utc':now(),'status':'completed_quarterly_sensitivity','quarters':13,'cases':len(rows),'shock':.2,'source_hashes':sources,
      'limitations':['DEX spot observations are quarter-end only and sparse; not a high-frequency or executable consolidated-price panel','Additional derivative haircuts 2/5/10% are assumptions, not calibrated depeg forecasts','No borrower response or sale feedback in this static stress','Independent full-history provider verification remains a separate requirement']}
    save(OUT/'h1/summary.json',result);return result

if __name__=='__main__':run()
