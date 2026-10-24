"""Synthetic fixtures only; never mixed into research data or results."""
import unittest,tempfile,json
from pathlib import Path
try:
    import numpy as np
    from defi_models.core import Portfolio,DEFAULTS,concentration,Data,sha,shock_grid,stamp
    from defi_models.statistics import hawkes_history,hawkes_score,breakpoint,glm,poisson_terms,poisson_predict
    from defi_models.simulation import cascade,pareto_screen,liquidation_profits
    from defi_models.__main__ import config,preflight
    from defi_models.analyses import temporal_positive
    MODEL_DEPENDENCIES=True
except ModuleNotFoundError:
    MODEL_DEPENDENCIES=False

def record(symbol,collateral=0,debt=0,lt=.8,account='wallet'):
    return dict(account=account,token=symbol,symbol=symbol,collateral_usd=str(collateral),debt_usd=str(debt),
                repayable_debt_usd=str(debt),effective_lt=str(lt))

@unittest.skipUnless(MODEL_DEPENDENCIES,'Install requirements-models.txt to test model estimators')
class ModelTests(unittest.TestCase):
    def setUp(self):self.cfg=dict(DEFAULTS)
    def test_both_sides_of_eth_debt_shocked(self):
        p=Portfolio([record('WETH',100,50)],self.cfg)
        self.assertAlmostEqual(p.stress()[0][0],p.stress(.5)[0][0])
        self.assertAlmostEqual(p.stress(.5)[1][0],25)
    def test_eth_collateral_stable_debt_threshold(self):
        p=Portfolio([record('WETH',100),record('USDC',debt=60)],self.cfg)
        self.assertGreater(p.stress(.2)[0][0],1)
        self.assertLess(p.stress(.3)[0][0],1)
    def test_disabled_collateral_not_added(self):
        p=Portfolio([record('WETH',0),record('USDC',debt=50)],self.cfg)
        self.assertEqual(p.stress()[0][0],0)
    def test_concentration_equal_and_single(self):
        self.assertAlmostEqual(concentration([1,1,1,1])['hhi'],.25)
        self.assertAlmostEqual(concentration([1,1,1,1])['gini'],0)
        self.assertEqual(concentration([5])['top1'],1)
        self.assertIsNone(concentration([])['hhi'])
    def test_no_self_excitation_within_tied_timestamp(self):
        t,m,h=hawkes_history(np.array([1.,1.,2.]),1)
        np.testing.assert_allclose(h,[0,2/np.e]);self.assertEqual(m[0],2)
    def test_hawkes_poisson_limit_and_holdout_history(self):
        t,m,h=hawkes_history(np.array([.5,1.,2.]),1)
        self.assertAlmostEqual(hawkes_score(t,m,h,2,0,1,1.5,3),np.log(2)-3)
        # Positive excitation from pre-test events contributes to compensator.
        expected=np.log(2+.2*h[-1])-3-.2*sum(n*(np.exp(-max(1.5-x,0))-np.exp(-(3-x))) for x,n in zip(t,m))
        self.assertAlmostEqual(hawkes_score(t,m,h,2,.2,1,1.5,3),expected)
    def test_piecewise_known_knot_and_flat(self):
        x=np.arange(0,1.01,.05);y=np.maximum(x-.4,0)*2
        self.assertAlmostEqual(breakpoint(x,y)['knot'],.4)
        self.assertFalse(breakpoint(x,np.zeros(len(x)))['identified'])
    def test_poisson_intercept_matches_sample_mean(self):
        y=np.array([0,1,2,3,4,5]);fit,mu=glm(np.ones((6,1)),y)
        self.assertTrue(fit.success);self.assertAlmostEqual(mu[0],y.mean(),places=5)
    def test_stable_portfolio_no_liquidation(self):
        p=Portfolio([record('WETH',100),record('USDC',debt=30)],self.cfg)
        r,h=cascade(p,.1,self.cfg);self.assertEqual(r['repaid_usd'],0);self.assertFalse(h)
    def test_liquidation_debt_conservation_zero_impact(self):
        p=Portfolio([record('WETH',100),record('USDC',debt=70)],self.cfg)
        r,h=cascade(p,.2,dict(self.cfg,impact_coefficient=0,gas_usd=0))
        self.assertGreater(r['repaid_usd'],0);self.assertLessEqual(r['repaid_usd'],70+1e-9)
        self.assertAlmostEqual(r['seized_usd'],r['repaid_usd']*1.05)
        self.assertAlmostEqual(sum(x['repaid_usd'] for x in h),r['repaid_usd'])
    def test_unprofitable_liquidation_does_not_execute(self):
        p=Portfolio([record('WETH',100),record('USDC',debt=70)],self.cfg)
        r,h=cascade(p,.2,dict(self.cfg,gas_usd=1000000))
        self.assertEqual(r['stop_reason'],'no_profitable_liquidations');self.assertEqual(r['repaid_usd'],0)
    def test_high_impact_cannot_make_negative_prices(self):
        p=Portfolio([record('WETH',100),record('USDC',debt=70)],self.cfg)
        r,h=cascade(p,.3,dict(self.cfg,impact_coefficient=10,liquidity_depth_usd=1,gas_usd=0))
        self.assertLessEqual(r['max_cumulative_price_impact'],self.cfg['impact_cap'])
        self.assertGreaterEqual(r['terminal_collateral_shortfall_usd'],0)
    def test_invalid_configuration_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'config.json';path.write_text(json.dumps({'shock_max':1}))
            with self.assertRaises(ValueError):config(path)
    def test_modified_frozen_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'processed').mkdir();p=root/'processed/test.csv';p.write_text('value\n1\n')
            (root/'freeze_manifest.json').write_text(json.dumps({'csv_files':[{'file':str(Path('processed/test.csv')),'sha256':sha(p)}]}))
            data=Data(root,self.cfg);self.assertEqual(data.read('test.csv')[0]['value'],'1')
            p.write_text('value\n2\n')
            with self.assertRaises(ValueError):Data(root,self.cfg).read('test.csv')
    def test_readonly_raw_database_connection(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'freeze_manifest.json').write_text('{"csv_files":[]}')
            c=sqlite3.connect(root/'history.sqlite');c.execute('CREATE TABLE example (value)');c.commit();c.close()
            c=Data(root,self.cfg).connection()
            with self.assertRaises(sqlite3.OperationalError):c.execute('INSERT INTO example VALUES (1)')
            c.close()
    def test_nan_balance_rejected(self):
        with self.assertRaises(ValueError):Portfolio([record('WETH',float('nan'))],self.cfg)
    def test_shock_grid_never_overshoots_and_includes_endpoint(self):
        grid=shock_grid(.6,.4);np.testing.assert_allclose(grid,[0,.4,.6])
        self.assertLessEqual(grid.max(),.6)
    def test_legacy_dust_hf_matches_protocol_rounding(self):
        a=record('WETH',.00001661,lt=.83);b=record('USDC',debt=.00001399)
        a['pool_revision']=b['pool_revision']='6'
        p=Portfolio([a,b],self.cfg);self.assertAlmostEqual(p.stress()[0][0],1379/1399,places=15)
    def test_tiny_lower_lt_collateral_changes_average_lt_floor(self):
        rs=[record('WETH',25005.21696889,19455.17904281,.83),record('wstETH',.0000002,0,.81),record('USDT',debt=859.78656219)]
        for r in rs:r['pool_revision']='6'
        self.assertAlmostEqual(Portfolio(rs,self.cfg).stress()[0][0],1.0215045383853605,places=12)
    def test_poisson_objective_gradient_consistent_at_extreme_trials(self):
        x=np.array([40.]);eps=1e-4;v,d=poisson_terms(x)
        finite=(poisson_terms(x+eps)[0]-poisson_terms(x-eps)[0])/(2*eps)
        np.testing.assert_allclose(d,finite,rtol=1e-8)
        with self.assertRaises(ValueError):poisson_predict([[1]],np.array([40.]))
    def test_future_recursive_label_cannot_mark_past_position(self):
        r={'label_available_at':'2025-02-03T00:00:00Z','borrow_stamp':stamp('2025-02-02T23:00:00Z'),'window_hours':'24'}
        self.assertFalse(temporal_positive(r,24,stamp('2025-02-02T23:59:59Z')))
        self.assertTrue(temporal_positive(r,24,stamp('2025-02-03T00:00:00Z')))
    def test_truncated_policy_does_not_dominate_completed_policy(self):
        a=dict(shock_fraction=.2,loss=0,reached_round_limit=True,terminal_eligible_wallets=1)
        b=dict(shock_fraction=.2,loss=10,reached_round_limit=False,terminal_eligible_wallets=0)
        pareto_screen([a,b],['loss']);self.assertIsNone(a['pareto_nondominated']);self.assertTrue(b['pareto_nondominated'])
    def test_stale_oracle_does_not_hide_existing_market_price_loss(self):
        cfg=dict(self.cfg,sell_fraction=0,impact_coefficient=.5,liquidity_depth_usd=100,gas_usd=0)
        profit,_,_=liquidation_profits(np.array([105.]),np.array([100.]),np.array([0]),np.array([100.]),np.array([.5]),np.array([1.]),np.array([1.]),cfg)
        self.assertLess(profit[0],0)
    def test_audit_json_alone_does_not_make_missing_dataset_pass(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for n,s in [(1,'structure'),(2,'onchain'),(3,'research')]:
                (root/f'audit_{n}_{s}.json').write_text('{"all_integrity_passed": true}')
            self.assertFalse(preflight(root,self.cfg,[2])['passed'])
    def test_bad_config_rejected_before_running_models(self):
        for change in [{'max_rounds':2.5},{'policy_bonuses':[]},{'liquidity_depth_usd':0},{'policy_close_factors':[1.1]},{'impact_coefficient':float('nan')},{'snapshot':3}]:
            with tempfile.TemporaryDirectory() as d:
                p=Path(d)/'config.json';p.write_text(json.dumps(change))
                with self.assertRaises(ValueError):config(p)
    def test_nonfinite_concentration_rejected(self):
        with self.assertRaises(ValueError):concentration([float('inf'),1])
    def test_naive_timestamp_rejected(self):
        with self.assertRaises(ValueError):stamp('2025-02-03T00:00:00')

if __name__=='__main__':unittest.main()
