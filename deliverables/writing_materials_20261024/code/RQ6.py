"""RQ6: stylized multi-round liquidation engine and zero-impact controls.

Also used by RQ7; all results retain explicit calibration limitations.
Run: python -m defi_models.rq6 --help
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
import numpy as np
from .core import require, write_csv, summary

def liquidation_profits(seized,amount,chosen,cumulative,impact,shock_factor,oracle_factor,cfg):
    # Depth is measured in initial post-shock USD, not a changing oracle numeraire.
    sale_notional=seized/oracle_factor[chosen]*shock_factor[chosen]*cfg['sell_fraction']
    sales=np.bincount(chosen,weights=sale_notional,minlength=len(impact))
    after=np.minimum(cfg['impact_cap'],cfg['impact_coefficient']*np.sqrt((cumulative+sales)/cfg['liquidity_depth_usd']))
    average_impact=(impact+after)/2
    # Market execution and oracle valuation can diverge when pass-through < 1.
    ratio=shock_factor[chosen]*(1-average_impact[chosen])/oracle_factor[chosen]
    proceeds=seized*ratio*(1-cfg['sell_fraction']*cfg.get('dex_fee_fraction',.003))
    return proceeds-amount-cfg['gas_usd'],sales,after

def cascade(portfolio,shock,cfg,close=None,bonus=None,lt_shift=0):
    p=portfolio;close=cfg['close_factor'] if close is None else close;bonus=cfg['liquidation_bonus'] if bonus is None else bonus
    require(0<close<=1 and 0<=bonus<1,'Invalid close factor/bonus')
    require(cfg['liquidity_depth_usd']>0 and 0<=cfg['sell_fraction']<=1,'Invalid liquidity depth/sell fraction')
    require(0<=cfg['oracle_pass_through']<=1 and 0<=cfg['impact_cap']<1,'Invalid impact parameters')
    c=p.c.copy();d=p.d.copy();repay=p.repay.copy();lt=np.clip(p.lt+lt_shift,0,1);shock_factor=p.factors(shock,shock)
    cumulative=np.zeros(len(p.tokens));impact=np.zeros(len(p.tokens));history=[];transactions=0;repaid_total=0.;seized_total=0.;profit_total=0.
    debt_initial=(repay*shock_factor).sum();initial_shortfall=np.maximum((repay*shock_factor).sum(axis=1)-(c*shock_factor).sum(axis=1),0).sum()
    ended='round_limit';residual=0
    for step in range(cfg['max_rounds']):
        f=shock_factor*(1-cfg['oracle_pass_through']*impact)
        cv=c*f;rv=(repay*f).sum(axis=1);risk=(d*f).sum(axis=1);weighted=(cv*lt).sum(axis=1)
        hf=np.divide(weighted,risk,out=np.full_like(risk,np.inf),where=risk>1e-8);eligible=(hf<1)&(rv>1e-6)
        if not eligible.any():ended='no_eligible_positions';break
        chosen=cv.argmax(axis=1);idx=np.arange(len(c));available=cv[idx,chosen]
        amount=np.minimum(close*rv,available/(1+bonus));amount=np.where(eligible,amount,0)
        seized=amount*(1+bonus)
        profits,_,_=liquidation_profits(seized,amount,chosen,cumulative,impact,shock_factor,f,cfg)
        execute=eligible&(amount>1e-6)&(profits>0)
        if not execute.any():ended='no_profitable_liquidations';break
        amount=np.where(execute,amount,0);seized=amount*(1+bonus)
        profits,sales,next_impact=liquidation_profits(seized,amount,chosen,cumulative,impact,shock_factor,f,cfg)
        require(np.all(profits[execute]>0),'Executed liquidation lost profitability after batch filtering')
        fraction=np.divide(amount,rv,out=np.zeros_like(rv),where=rv>0)
        before_risk=d.sum();before_repay=repay.sum()
        d*=1-fraction[:,None];repay*=1-fraction[:,None]
        decrement=np.divide(seized,f[chosen],out=np.zeros_like(seized),where=f[chosen]>0)
        c[idx,chosen]-=decrement
        require(c.min()>-1e-5 and d.min()>-1e-5 and repay.min()>-1e-5,'Simulation balance became negative')
        c=np.maximum(c,0);d=np.maximum(d,0);repay=np.maximum(repay,0)
        require(d.sum()<=before_risk+1e-5 and repay.sum()<=before_repay+1e-5,'Debt increased during repayment')
        cumulative+=sales;impact=next_impact
        n=int(execute.sum());transactions+=n;repaid_total+=amount.sum();seized_total+=seized.sum();profit_total+=profits[execute].sum()
        history.append(dict(round=step+1,eligible_before=int(eligible.sum()),executed_wallet_actions=n,repaid_usd=amount.sum(),collateral_seized_usd=seized.sum(),
             max_cumulative_price_impact=impact.max(),liquidator_profit_usd=profits[execute].sum()))
    f=shock_factor*(1-cfg['oracle_pass_through']*impact);risk=(d*f).sum(axis=1);weighted=(c*f*lt).sum(axis=1)
    residual=int(((weighted<risk)&(risk>1e-6)).sum())
    if ended=='round_limit' and residual==0:ended='no_eligible_positions'
    shortfall=np.maximum((repay*f).sum(axis=1)-(c*f).sum(axis=1),0).sum()
    result=dict(shock_fraction=shock,close_factor=close,bonus_fraction=bonus,lt_shift=lt_shift,rounds=len(history),stop_reason=ended,
         executed_wallet_actions=transactions,repaid_usd=repaid_total,seized_usd=seized_total,liquidator_profit_usd=profit_total,
         initial_repayable_debt_usd=debt_initial,initial_collateral_shortfall_usd=initial_shortfall,
         terminal_collateral_shortfall_usd=shortfall,terminal_eligible_wallets=residual,
         max_cumulative_price_impact=impact.max(),reached_round_limit=ended=='round_limit')
    return result,history

LIMITS=['Stylized simulator, not historical Aave execution or a validated full-system model',
 'Each wallet action repays a proportional debt basket and seizes the largest available enabled collateral; real Aave requires a chosen debt/collateral pair',
 'Generic uniform liquidity depth and square-root impact are user assumptions, not calibrated historical liquidity',
 'No cross-DEX routing, intra-block ordering, flash-loan constraints or exact GHO risk/repayment conversion',
 'Synchronous batch profitability uses tentative all-eligible sales; exclusions can make this a conservative execution screen',
 'Terminal collateral shortfall is a model accounting measure, not recorded on-chain bad debt',
 'No-policy-shock LT comparisons hold original balances fixed; they omit borrower responses']

def rq6(data,out,cfg):
    p,scope=data.snapshot();all_results=[];histories=[]
    for shock in cfg['cascade_shocks']:
        r,h=cascade(p,shock,cfg);all_results.append(r);histories.extend([dict(shock_fraction=shock,case='assumed_impact',**x) for x in h])
        # Explicit zero-impact control at identical financial assumptions.
        r0,h0=cascade(p,shock,dict(cfg,impact_coefficient=0));r0['case']='zero_impact_control';r['case']='assumed_impact';all_results.append(r0)
        histories.extend([dict(shock_fraction=shock,case='zero_impact_control',**x) for x in h0])
    write_csv(out/'cascade_scenarios.csv',all_results);write_csv(out/'cascade_rounds.csv',histories)
    return summary('exploratory','Liquidation cascade sensitivity with no-impact controls',LIMITS,snapshot=scope,
                   liquidity_depth_usd=cfg['liquidity_depth_usd'],historical_quote_calibration=False,scenarios=len(all_results),
                   warnings=[f'{sum(r["reached_round_limit"] for r in all_results)} scenarios reached round limit; not terminal equilibrium'] if any(r['reached_round_limit'] for r in all_results) else [])

def main(argv=None):
    from . import __main__ as _runner
    _runner.MODELS.update({6: rq6})
    from .member_cli import run_member
    return run_member([6], argv)


if __name__ == "__main__":
    raise SystemExit(main())
