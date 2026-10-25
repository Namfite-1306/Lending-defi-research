"""Offline denominator/newly-eligible sensitivity; never promotes partial census."""
import numpy as np
from .repair_common import *
from defi_models.core import Portfolio,DEFAULTS

def run():
    out=OUT/'h1';rows=[];full=[]
    for item in load(H1_DATA/'h1/quarter_plan.json',[]):
        folder=H1_DATA/'h1'/item['quarter'];scope=load(folder/'scope.json',{})
        if not scope.get('full_snapshot_complete'):continue
        freeze=load(folder/'freeze_manifest.json',{})
        if not freeze or not all(digest(folder/n)==h for n,h in freeze['files'].items()):raise ValueError('Quarter freeze mismatch')
        records=read(folder/'positions.csv');full.append(item['quarter'])
        for mapping,cfg in [('factor_family_1to1',DEFAULTS),('direct_WETH_WBTC_only',dict(DEFAULTS,eth_symbols=['WETH'],btc_symbols=['WBTC']))]:
            p=Portfolio(records,cfg);hf0,d0=p.stress();pre=float(d0.sum())
            for scenario,eth,btc in [('joint',1,1),('ETH_only',1,0),('BTC_only',0,1)]:
                for shock in [0,.1,.2,.3,.4,.5,.6]:
                    hf,d=p.stress(shock*eth,shock*btc);eligible=hf<1;new=eligible&(hf0>=1);post=float(d.sum())
                    rows.append({'quarter':item['quarter'],'mapping':mapping,'scenario':scenario,'shock':shock,'pre_shock_total_debt_usd':pre,'post_shock_total_debt_usd':post,
                      'initially_eligible_wallets':int((hf0<1).sum()),'eligible_wallets':int(eligible.sum()),'newly_eligible_wallets':int(new.sum()),
                      'eligible_post_debt_over_post_total':float(d[eligible].sum()/post),'eligible_post_debt_over_pre_total':float(d[eligible].sum()/pre),
                      'newly_eligible_post_debt_over_pre_total':float(d[new].sum()/pre),'newly_eligible_pre_debt_over_pre_total':float(d0[new].sum()/pre)})
    write(out/'denominator_sensitivity.csv',rows)
    result={'updated_utc':now(),'full_quarters':full,'required':15,'rows':len(rows),'status':'partial_full_snapshots_only',
      'limitations':['Static stress, not realized liquidation volume','Factor-family basis and direct-only are assumptions, not observed depeg','Missing two quarters remain excluded']}
    save(out/'summary.json',result);return result

if __name__=='__main__':print(run())
