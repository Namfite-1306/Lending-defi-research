"""Available-data runners preserve sample scope and stop before coverage gaps."""
import csv
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

try:
    from defi_models.available_rq14 import sample_portfolio,prefix_events,fit_prefix,run
    from defi_models.core import DEFAULTS,stamp
    MODEL_DEPS=True
except ModuleNotFoundError:
    MODEL_DEPS=False


@unittest.skipUnless(MODEL_DEPS,'Install requirements-models.txt')
class AvailableTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.p=self.root/'processed';self.p.mkdir()

    def write(self,name,records):
        with (self.p/name).open('w',newline='',encoding='utf8') as f:
            w=csv.DictWriter(f,fieldnames=records[0]);w.writeheader();w.writerows(records)

    def sample(self):
        (self.p/'position_scope.json').write_text(json.dumps({'block':21762264,'full_universe':False}))
        self.write('positions_point_in_time_sample.csv',[dict(account='wallet',block_number=21762264,token_address='token',symbol='WETH',collateral_usd=100,debt_usd=50,
            effective_liquidation_threshold=.8,price_usd=1,repayable_debt_raw=50,pool_revision=6,validation_passed=True)])
        self.write('position_checks.csv',[dict(account='wallet',block_number=21762264,passed=True,reported_debt_usd=50,hf_reported=1.6,max_relative_error=0)])
        self.write('historical_reserve_config_sample.csv',[dict(token_address='token',symbol='WETH',block_number=21762264,decimals=0,price=1)])

    def test_valid_sample_reconciles_but_is_never_a_full_snapshot(self):
        self.sample();p,scope,_=sample_portfolio(self.root,dict(DEFAULTS))
        self.assertAlmostEqual(p.stress()[0][0],1.6)
        self.assertFalse(scope['full_universe']);self.assertFalse(scope['full_snapshot_complete'])

    def test_wrong_hf_and_cross_block_metadata_are_rejected(self):
        self.sample()
        self.write('position_checks.csv',[dict(account='wallet',block_number=21762264,passed=True,reported_debt_usd=50,hf_reported=2,max_relative_error=0)])
        with self.assertRaisesRegex(ValueError,'HF does not reconcile'):sample_portfolio(self.root,dict(DEFAULTS))
        self.sample()
        self.write('historical_reserve_config_sample.csv',[dict(token_address='token',symbol='WETH',block_number=21762265,decimals=0,price=1)])
        with self.assertRaisesRegex(ValueError,'same|sample block'):sample_portfolio(self.root,dict(DEFAULTS))

    def prefix(self):
        c=sqlite3.connect(':memory:');self.addCleanup(c.close)
        c.executescript('CREATE TABLE ranges(protocol,lo,hi); CREATE TABLE events(protocol,name,block,stamp,tx,txidx,idx,hash);')
        c.executemany('INSERT INTO ranges VALUES (?,?,?)',[('aave_v3',100,500),('aave_v3',600,1000)])
        start=int(stamp('2025-01-01T00:00:00+00:00'))
        c.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',('aave_v3','Borrow',100,start+1,'first',0,0,'h'))
        for i in range(100):c.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',('aave_v3','LiquidationCall',101+3*i,start+(2+8*i)*3600,'tx'+str(i),0,i,'h'))
        c.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?)',('aave_v3','LiquidationCall',700,start+1000*3600,'after_gap',0,100,'h'))
        c.commit()
        bounds={'start_block':100,'end_block':1000,'start_utc':'2025-01-01T00:00:00+00:00','end_exclusive_utc':'2025-03-01T00:00:00+00:00'}
        boundary=lambda n:{'number':hex(n),'hash':'h','timestamp':hex(start+960*3600)}
        return c,bounds,boundary,start

    def test_prefix_excludes_gap_and_partial_first_hour(self):
        c,b,header,origin=self.prefix();start,end,events,scope=prefix_events(c,b,header)
        self.assertEqual(start,origin+3600);self.assertEqual(end,origin+960*3600)
        self.assertEqual(len(events),100);self.assertNotIn('after_gap',{r['tx'] for r in events})
        self.assertEqual(scope['prefix_end_block'],500);self.assertFalse(scope['full_requested_period'])

    def test_missing_leading_coverage_is_not_zero_filled(self):
        c,b,header,_=self.prefix();c.execute('DELETE FROM ranges WHERE lo=100');c.commit()
        with self.assertRaisesRegex(ValueError,'leading'):prefix_events(c,b,header)

    def test_prefix_fit_is_exploratory_and_has_no_price_controls(self):
        c,b,header,_=self.prefix();start,end,events,_=prefix_events(c,b,header)
        out=self.root/'rq4';out.mkdir();result=fit_prefix(start,end,events,dict(DEFAULTS),out)
        self.assertEqual(result['status'],'exploratory');self.assertFalse(result['poisson']['price_controls_included'])
        self.assertTrue(result['hawkes']['converged']);self.assertEqual(result['events'],100)

    def test_both_reports_complete_with_real_summary_schema_and_keep_scope(self):
        self.sample();c,b,header,_=self.prefix();data=self.root/'history';data.mkdir()
        disk=sqlite3.connect(data/'history.sqlite')
        try:c.backup(disk)
        finally:disk.close()
        (data/'block_range.json').write_text(json.dumps(b))
        out=self.root/'result';manifest=run(self.root,data,dict(DEFAULTS),out,header)
        self.assertTrue(manifest['all_executed']);self.assertFalse(manifest['full_research_ready'])
        self.assertTrue((out/'RUN_REPORT.md').is_file());self.assertTrue(manifest['code_files'])
        for rq in [1,4]:
            result=json.loads((out/f'rq{rq}/summary.json').read_text())
            self.assertEqual(result['status'],'exploratory')
        self.assertEqual(json.loads((out/'rq1/summary.json').read_text())['sample_wallets'],1)
