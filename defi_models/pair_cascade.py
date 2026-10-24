"""Experimental pair-specific revision-6 sensitivity engine.

Keeps the published RQ6 engine unchanged. Not an EVM transaction replica.
No claim of historical calibration; quote curves live in stress_validation.
"""
import numpy as np
from .core import require


def pair_cascade(p,shock,cfg):
    require(np.all(p.revisions==6),'Pair engine currently supports only revision-6 snapshot; do not apply to newer pools')
    require(0<=shock<1 and 0<cfg['close_factor']<=1,'Invalid shock/close factor')
    require(cfg['liquidity_depth_usd']>0 and cfg['max_rounds']>0,'Invalid depth/rounds')
    require(0<=cfg['oracle_pass_through']<=1 and 0<=cfg['impact_cap']<1 and cfg['impact_coefficient']>=0,'Invalid impact settings')
    require(cfg.get('oracle_delay_rounds',0)>=0 and isinstance(cfg.get('oracle_delay_rounds',0),int),'Invalid oracle delay')
    require(0<=cfg['liquidation_bonus']<1 and cfg['gas_usd']>=0,'Invalid bonus/gas')
    c=p.c.copy();d=p.d.copy();repay=p.repay.copy();initial=p.factors(shock,shock)
    impact=np.zeros(len(p.tokens));cumulative=np.zeros(len(p.tokens));past=[impact.copy()];history=[];actions=[]
    ix=np.arange(len(c));ended='round_limit'
    for step in range(cfg['max_rounds']):
        delay=cfg.get('oracle_delay_rounds',0);observed=past[max(0,len(past)-1-delay)]
        f=initial*(1-cfg['oracle_pass_through']*observed)
        cv=c*f;dv=d*f;rv=repay*f;risk=dv.sum(axis=1)
        hf=np.divide((cv*p.lt).sum(axis=1),risk,out=np.full_like(risk,np.inf),where=risk>1e-8)
        eligible=(hf<1)&(rv.sum(axis=1)>1e-6)
        pending=np.max(np.abs(impact-observed))>1e-12
        if not eligible.any():
            if pending:
                past.append(impact.copy());history.append({'round':step+1,'executed_pairs':0,'repaid_usd':0.,'seized_usd':0.,
                  'max_market_impact':float(impact.max()),'max_oracle_impact':float((cfg['oracle_pass_through']*observed).max())})
                continue
            ended='no_eligible_positions';break
        collateral=cv.argmax(axis=1);debt=rv.argmax(axis=1)
        # Legacy V3 close factor applies to the selected debt reserve, not a
        # proportional basket. Configured lower close factor is a counterfactual.
        close=np.where(hf<=.95,1.,cfg['close_factor'])
        bonus=np.array([cfg.get('bonus_by_account_token',{}).get(p.accounts[i],{}).get(p.tokens[j],cfg.get('bonus_by_token',{}).get(p.tokens[j],cfg['liquidation_bonus'])) for i,j in enumerate(collateral)])
        require(np.isfinite(bonus).all() and np.all((bonus>=0)&(bonus<1)),'Invalid reserve bonus')
        amount=np.where(eligible,np.minimum(close*rv[ix,debt],cv[ix,collateral]/(1+bonus)),0.)
        seized=amount*(1+bonus)
        protocol_fee=np.array([cfg.get('protocol_fee_by_token',{}).get(p.tokens[j],0.) for j in collateral])
        require(np.all((protocol_fee>=0)&(protocol_fee<=1)),'Invalid protocol fee')
        received=amount*(1+bonus*(1-protocol_fee))
        sold=received/f[collateral]*initial[collateral]
        def execution(mask):
            sales=np.bincount(collateral,weights=np.where(mask,sold,0.),minlength=len(p.tokens))
            after=np.minimum(cfg['impact_cap'],cfg['impact_coefficient']*np.sqrt((cumulative+sales)/cfg['liquidity_depth_usd']))
            average=(impact+after)/2
            fee=cfg.get('dex_fee_fraction',.003)
            proceeds=received*initial[collateral]*(1-average[collateral])/f[collateral]*(1-fee)
            # Repayment costs use contemporaneous market value of the chosen
            # debt asset, keeping DEX prices distinct from oracle valuation.
            cost=amount*initial[debt]*(1-impact[debt])/f[debt]
            return proceeds-cost-cfg['gas_usd'],sales,after
        proposed=eligible&(amount>1e-6);profit,_,_=execution(proposed)
        executed=proposed&(profit>0)
        if not executed.any():
            if pending:
                past.append(impact.copy());history.append({'round':step+1,'executed_pairs':0,'repaid_usd':0.,'seized_usd':0.,
                  'max_market_impact':float(impact.max()),'max_oracle_impact':float((cfg['oracle_pass_through']*observed).max())})
                continue
            ended='no_profitable_pairs';break
        profit,sales,after=execution(executed)
        require(np.all(profit[executed]>0),'Batch filtering changed pair profitability')
        selected=np.flatnonzero(executed)
        for i in selected:
            j=debt[i];k=collateral[i];fraction=amount[i]/rv[i,j]
            before_c=c[i,k];before_d=d[i,j];before_repay=repay[i,j]
            c[i,k]-=seized[i]/f[k];d[i,j]*=1-fraction;repay[i,j]*=1-fraction
            actions.append({'round':step+1,'account':p.accounts[i],'debt_token':p.tokens[j],'collateral_token':p.tokens[k],
              'repaid_usd':float(amount[i]),'seized_usd':float(seized[i]),'hf_before':float(hf[i]),'close_factor':float(close[i]),
              'bonus':float(bonus[i]),'profit_usd':float(profit[i]),
              'received_collateral_usd':float(received[i]),'protocol_fee_collateral_usd':float(seized[i]-received[i]),
              'collateral_decrement_base_usd':float(before_c-c[i,k]),'risk_debt_decrement_base_usd':float(before_d-d[i,j]),
              'repayable_decrement_base_usd':float(before_repay-repay[i,j])})
        require(c.min()>-1e-5 and d.min()>-1e-5 and repay.min()>-1e-5,'Negative pair balance')
        c=np.maximum(c,0);d=np.maximum(d,0);repay=np.maximum(repay,0)
        cumulative+=sales;impact=after;past.append(impact.copy())
        history.append({'round':step+1,'executed_pairs':len(selected),'repaid_usd':float(amount[executed].sum()),
          'seized_usd':float(seized[executed].sum()),'max_market_impact':float(impact.max()),
          'max_oracle_impact':float((cfg['oracle_pass_through']*observed).max())})
    observed=past[max(0,len(past)-1-cfg.get('oracle_delay_rounds',0))];f=initial*(1-cfg['oracle_pass_through']*observed)
    risk=(d*f).sum(axis=1);residual=int((((c*f*p.lt).sum(axis=1)<risk)&(risk>1e-6)).sum())
    if ended=='round_limit' and not residual and np.max(np.abs(impact-observed))<=1e-12:ended='no_eligible_positions'
    return {'engine':'experimental_pair_revision6','shock':shock,'rounds':len(history),'stop_reason':ended,
      'executed_pairs':len(actions),'repaid_usd':sum(a['repaid_usd'] for a in actions),
      'terminal_eligible_wallets':residual,'terminal_collateral_shortfall_usd':float(np.maximum((repay*f).sum(axis=1)-(c*f).sum(axis=1),0).sum()),
      'historically_calibrated':False,'oracle_delay_rounds':cfg.get('oracle_delay_rounds',0),
      'limitation':'Largest debt/collateral pair per round; assumed bonuses/depth/ordering/round delay, float arithmetic, no exact EVM or flash-loan replay'},history,actions
