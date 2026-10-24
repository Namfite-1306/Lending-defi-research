"""Dashboard calculations and UI are tested with synthetic, local-only fixtures."""
import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

DEPS=all(importlib.util.find_spec(n) is not None for n in ['streamlit','pandas','numpy','scipy'])
if DEPS:
    import pandas as pd
    from streamlit.testing.v1 import AppTest
    from defi_models.core import ROOT,DEFAULTS,sha
    from defi_models.dashboard_data import aggregate_counts,decay_response,stress_view,validated_portfolio


@unittest.skipUnless(DEPS,'Install requirements-dashboard.txt')
class DashboardTests(unittest.TestCase):
    def setUp(self):
        temp_root=ROOT/'data/test_tmp';temp_root.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=temp_root)
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.sources=self.root/'sample/processed';self.sources.mkdir(parents=True)
        self.results=self.root/'results';self.run=self.results/'fixture';self.run.mkdir(parents=True)
        for rq in [1,4]:(self.run/f'rq{rq}').mkdir()
        self.json(self.sources/'position_scope.json',{'block':21762264})
        self.csv(self.sources/'positions_point_in_time_sample.csv',[
            dict(account='wallet',block_number=21762264,token_address='weth',symbol='WETH',collateral_usd=100,debt_usd=0,effective_liquidation_threshold=.8,price_usd=1,repayable_debt_raw=0,pool_revision=6,validation_passed=True),
            dict(account='wallet',block_number=21762264,token_address='usdc',symbol='USDC',collateral_usd=0,debt_usd=50,effective_liquidation_threshold=0,price_usd=1,repayable_debt_raw=50,pool_revision=6,validation_passed=True),
        ])
        self.csv(self.sources/'position_checks.csv',[dict(account='wallet',block_number=21762264,passed=True,reported_debt_usd=50,hf_reported=1.6,max_relative_error=0)])
        self.csv(self.sources/'historical_reserve_config_sample.csv',[
            dict(token_address='weth',symbol='WETH',block_number=21762264,decimals=0,price=1),
            dict(token_address='usdc',symbol='USDC',block_number=21762264,decimals=0,price=1)])
        self.json(self.run/'manifest.json',{'config':dict(DEFAULTS),'models':[{'rq':i,'execution':'completed'} for i in [1,4]],
            'source_files':[{'path':str(p),'sha256':sha(p)} for p in self.sources.iterdir()]})
        self.json(self.run/'rq1/summary.json',{'snapshot':{'block':21762264},'sample_wallets':1,'baseline_total_risk_debt_usd':50})
        self.csv(self.run/'rq1/stress_curve.csv',[dict(scenario='ETH_only',shock_fraction=0,eligible_risk_debt_usd=0),dict(scenario='ETH_only',shock_fraction=.4,eligible_risk_debt_usd=50)])
        self.csv(self.run/'rq1/factor_mapping.csv',[dict(token='weth',symbol='WETH',factor='ETH')])
        self.json(self.run/'rq4/summary.json',{'events':2,'hours':3,'observation_start_utc':'2025-01-01T00:00:00+00:00',
            'observation_end_exclusive_utc':'2025-01-01T03:00:00+00:00','train_end_utc':'2025-01-01T02:00:00+00:00',
            'hawkes':{'half_life_hours':1/12,'branching_ratio':.8,'baseline_per_hour':.1}})
        self.csv(self.run/'rq4/hourly_counts.csv',[dict(hour_utc=f'2025-01-01T0{i}:00:00+00:00',liquidation_events=n,sample='train' if i<2 else 'test') for i,n in enumerate([0,2,0])])
        self.csv(self.run/'rq4/hawkes_candidates.csv',[dict(half_life_hours=1/12,branching_ratio=.8,converged=True)])

    def json(self,path,obj):path.write_text(json.dumps(obj),encoding='utf8')
    def csv(self,path,records):
        with path.open('w',encoding='utf8',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=records[0]);writer.writeheader();writer.writerows(records)

    def app(self):
        with patch.dict('os.environ',{'DEFI_DASHBOARD_RESULTS':str(self.results)}):
            return AppTest.from_file(str(ROOT/'streamlit_app.py'),default_timeout=20).run()

    def test_scenario_zero_and_stress_match_expected_hf(self):
        p,_=validated_portfolio(self.run)
        baseline=stress_view(p,0,0);stressed=stress_view(p,.4,0)
        self.assertEqual(baseline['eligible_wallets'],0)
        self.assertAlmostEqual(baseline['wallets']['HF kịch bản'][0],1.6)
        self.assertEqual(stressed['eligible_wallets'],1)
        self.assertAlmostEqual(stressed['wallets']['HF kịch bản'][0],.96)
        self.assertEqual(stressed['eligible_debt'],50)

    def test_changed_source_is_rejected_before_simulation(self):
        path=self.sources/'position_checks.csv'
        path.write_text(path.read_text()+'\n',encoding='utf8')
        with self.assertRaisesRegex(ValueError,'Source file changed'):validated_portfolio(self.run)

    def test_hawkes_response_halves_excess_after_one_half_life(self):
        frame=decay_response(.1,.8,5,3,10)
        start=frame.iloc[0]['Cường độ giả định (sự kiện/giờ)']-.1
        middle=frame.iloc[120]['Cường độ giả định (sự kiện/giờ)']-.1
        self.assertAlmostEqual(middle,start/2)
        for n in [-.1,1,float('nan')]:
            with self.assertRaises(ValueError):decay_response(.1,n,5,3)

    def test_aggregation_keeps_observed_hours_and_event_totals(self):
        panel=pd.read_csv(self.run/'rq4/hourly_counts.csv');panel['hour_utc']=pd.to_datetime(panel['hour_utc'],utc=True)
        result=aggregate_counts(panel,'2025-01-01','2025-01-01')
        self.assertEqual(result['Số thanh lý'].sum(),2)
        self.assertEqual(result['Giờ quan sát'].sum(),3)

    def test_navigation_and_price_slider_change_actual_metrics(self):
        with patch.dict('os.environ',{'DEFI_DASHBOARD_RESULTS':str(self.results)}):
            app=self.app();self.assertFalse(app.exception)
            app.segmented_control(key='section').set_value('RQ1 · Stress vị thế').run()
            self.assertFalse(app.exception)
            self.assertEqual(app.metric[0].value,'1/1')
            app.slider(key='eth_shock').set_value(0).run()
            self.assertFalse(app.exception);self.assertEqual(app.metric[0].value,'0/1')
            app.segmented_control(key='section').set_value('RQ4 · Nhịp thanh lý').run()
            self.assertFalse(app.exception)
            app.slider(key='burst').set_value(10).run()
            self.assertFalse(app.exception)
            app.segmented_control(key='section').set_value('Giả định & dữ liệu').run()
            self.assertFalse(app.exception)

    def test_empty_results_shows_instruction_without_exception(self):
        empty=self.root/'empty';empty.mkdir()
        with patch.dict('os.environ',{'DEFI_DASHBOARD_RESULTS':str(empty)}):
            app=AppTest.from_file(str(ROOT/'streamlit_app.py'),default_timeout=20).run()
        self.assertFalse(app.exception);self.assertTrue(app.info)
