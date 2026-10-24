"""RQ7 policy grid using the shared RQ6 engine; compatible public imports."""
import itertools
from .core import write_csv, summary
from .rq6 import cascade, liquidation_profits, LIMITS, rq6

def pareto_screen(results,objectives):
    valid=[r for r in results if not r['reached_round_limit']]
    for r in results:
        r['pareto_evaluable']=not r['reached_round_limit']
        r['pareto_nondominated']=None if not r['pareto_evaluable'] else not any(
            all(q[k]<=r[k] for k in objectives) and any(q[k]<r[k] for k in objectives)
            for q in valid if q['shock_fraction']==r['shock_fraction'])
        r['incomplete_dynamics']=r['reached_round_limit'] or r['terminal_eligible_wallets']>0

def rq7(data,out,cfg):
    p,scope=data.snapshot();results=[]
    for shock,close,bonus,shift in itertools.product(cfg['cascade_shocks'],cfg['policy_close_factors'],cfg['policy_bonuses'],cfg['policy_lt_shifts']):
        result,_=cascade(p,shock,cfg,close=close,bonus=bonus,lt_shift=shift);results.append(result)
    # Pareto screen within each identical shock, avoiding an arbitrary weighted score.
    objectives=['terminal_collateral_shortfall_usd','seized_usd','max_cumulative_price_impact']
    pareto_screen(results,objectives)
    write_csv(out/'policy_grid.csv',results)
    return summary('exploratory','Policy grid and Pareto screen conditional on the stylized engine',LIMITS+[
        'Pareto objectives minimize shortfall, seized collateral and price impact; no globally optimal protocol parameter recommendation',
        'Read residual eligibility and round-limit flags before interpreting low-liquidation candidates'],snapshot=scope,
        objective_names=objectives,scenarios=len(results),historical_policy_replay=False,
        warnings=[f'{sum(r["reached_round_limit"] for r in results)} scenarios reached round limit and were excluded from Pareto screening'] if any(r['reached_round_limit'] for r in results) else [])
