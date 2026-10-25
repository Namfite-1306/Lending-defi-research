"""Exposure composition/concentration of stressed accounts, not causal attribution."""
import numpy as np
from defi_models.core import Portfolio,DEFAULTS,concentration
from .v2_common import *

def run():
    out=OUT/'h1_attribution';all_composition=[];all_wallets=[];all_concentration=[];complete=[]
    for item in load(H1_DATA/'h1/quarter_plan.json',[]):
        folder=H1_DATA/'h1'/item['quarter'];scope=load(folder/'scope.json',{})
        if not scope.get('full_snapshot_complete'):continue
        freeze=load(folder/'freeze_manifest.json',{})
        if not freeze or any(digest(folder/name)!=value for name,value in freeze['files'].items()):raise ValueError('Quarter freeze mismatch')
        dest=out/item['quarter'];identity={'freeze_sha256':digest(folder/'freeze_manifest.json'),'code_sha256':digest(__file__)}
        if load(dest/'identity.json')==identity:
            composition=read(dest/'token_composition.csv');wallets=read(dest/'top_wallets.csv');conc=read(dest/'concentration.csv')
        else:
            p=Portfolio(read(folder/'positions.csv'),DEFAULTS);base,_=p.stress();composition=[];wallets=[];conc=[]
            for scenario,eth,btc in [('ETH_only',1,0),('BTC_only',0,1),('joint',1,1)]:
                for shock in [0.,.1,.2,.3]:
                    hf,debt=p.stress(shock*eth,shock*btc);eligible=hf<1;new=(base>=1)&eligible;f=p.factors(shock*eth,shock*btc)
                    weights=debt[eligible];stats=concentration(weights)
                    common={'quarter':item['quarter'],'block':item['block'],'scenario':scenario,'shock':shock}
                    conc.append(dict(**common,eligible_wallets=int(eligible.sum()),newly_eligible_wallets=int(new.sum()),newly_eligible_debt_usd=float(debt[new].sum()),
                      eligible_debt_usd=float(weights.sum()),**{k:(v.item() if isinstance(v,np.generic) else v) for k,v in stats.items()},
                      interpretation='Address concentration and exposure composition, not beneficial owners or causal token effects'))
                    for side,matrix in [('collateral',p.c),('debt',p.d)]:
                        amounts=(matrix[eligible]*f).sum(axis=0);total=float(amounts.sum())
                        for token,symbol,amount in zip(p.tokens,p.symbols,amounts):
                            if amount>0:composition.append(dict(**common,side=side,token=token,symbol=symbol,usd=float(amount),share=float(amount/total)))
                    indices=np.flatnonzero(eligible);order=indices[np.argsort(-debt[eligible])[:20]]
                    for rank,i in enumerate(order,1):wallets.append(dict(**common,rank=rank,account=p.accounts[i],debt_usd=float(debt[i]),hf=float(hf[i]),newly_eligible=bool(new[i]),eligible_debt_share=float(debt[i]/weights.sum())))
            write(dest/'token_composition.csv',composition);write(dest/'top_wallets.csv',wallets);write(dest/'concentration.csv',conc);save(dest/'identity.json',identity)
        complete.append(item['quarter']);all_composition+=composition;all_wallets+=wallets;all_concentration+=conc
    write(out/'token_composition.csv',all_composition);write(out/'top_wallets.csv',all_wallets);write(out/'concentration.csv',all_concentration)
    summary={'updated_utc':now(),'full_quarters':len(complete),'complete_quarters':complete,'status':'completed_scoped' if len(complete)==15 else 'partial_full_only',
      'limitations':['Stress debt eligible for liquidation, not realized liquidation sales','Token composition is exposure, not causal attribution','Addresses are not necessarily beneficial owners','ETH/BTC family mapping assumes 1:1 factor sensitivities']}
    save(out/'summary.json',summary);return summary
if __name__=='__main__':run()
