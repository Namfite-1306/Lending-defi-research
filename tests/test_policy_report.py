"""Policy exports must preserve provenance, scope, truncation and actual numbers."""
import importlib
import itertools
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from defi_models.core import write_csv, write_json
from defi_models.policy_report import generate


class PolicyReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.run=self.root/'run';(self.run/'rq7').mkdir(parents=True)
        self.cfg=dict(cascade_shocks=[.1,.2,.3],policy_close_factors=[.25,.5,1.],
                      policy_bonuses=[.03,.05,.08],policy_lt_shifts=[-.03,0.,.03],max_rounds=200)
        self.grid=[]
        for shock,close,bonus,shift in itertools.product(*[self.cfg[k] for k in ('cascade_shocks','policy_close_factors','policy_bonuses','policy_lt_shifts')]):
            self.grid.append(dict(shock_fraction=shock,close_factor=close,bonus_fraction=bonus,lt_shift=shift,
                repaid_usd=1000,seized_usd=1050,terminal_collateral_shortfall_usd=123.45,
                max_cumulative_price_impact=.01,liquidator_profit_usd=10,reached_round_limit=False,
                pareto_evaluable=True,pareto_nondominated=False,incomplete_dynamics=True,
                terminal_eligible_wallets=1,stop_reason='no_profitable_liquidations'))
        self.manifest=dict(all_executed=True,models=[dict(rq=7,execution='completed')],config=self.cfg,versions={})
        self.save()

    def save(self):
        write_json(self.run/'manifest.json',self.manifest)
        write_json(self.run/'config.json',self.cfg)
        write_json(self.run/'rq7/summary.json',dict(status='exploratory',scenarios=len(self.grid),snapshot=dict(block=1,active_debt_wallets=5)))
        write_csv(self.run/'rq7/policy_grid.csv',self.grid)

    def test_actual_numbers_and_hashes_are_exported(self):
        target=self.root/'export';meta=generate(self.run,target)
        self.assertIn('123.45',(target/'RQ7_REPORT.md').read_text(encoding='utf8'))
        self.assertEqual(meta['snapshot']['active_debt_wallets'],5)
        self.assertEqual(len(meta['source_files']),3)
        self.assertEqual(len(meta['files']),3)
        self.assertEqual(meta['missing_named_scenarios'],[])

    def test_truncated_pareto_remains_unknown(self):
        r=next(r for r in self.grid if (r['shock_fraction'],r['close_factor'],r['bonus_fraction'],r['lt_shift'])==(.1,.5,.05,0.))
        r.update(reached_round_limit=True,pareto_evaluable=False,pareto_nondominated=None,stop_reason='round_limit')
        self.save();target=self.root/'export';generate(self.run,target)
        self.assertIn('Chưa đánh giá',(target/'RQ7_REPORT.md').read_text(encoding='utf8'))
        self.assertIn('round_limit',(target/'sensitivity_results.csv').read_text(encoding='utf-8-sig'))

    def test_source_config_mismatch_stops_before_writes(self):
        cfg=dict(self.cfg,max_rounds=20);write_json(self.run/'config.json',cfg)
        with self.assertRaisesRegex(ValueError,'config differs'):generate(self.run,self.root/'bad')
        self.assertFalse((self.root/'bad').exists())

    def test_duplicate_and_nonfinite_rows_are_rejected(self):
        self.grid.append(dict(self.grid[0]));self.save()
        with self.assertRaisesRegex(ValueError,'Duplicate'):generate(self.run,self.root/'duplicate')
        self.grid.pop();self.grid[0]['seized_usd']='nan';self.save()
        with self.assertRaisesRegex(ValueError,'financial'):generate(self.run,self.root/'nan')

    def test_no_silent_overwrite_or_import_writes(self):
        dest=self.root/'export';generate(self.run,dest)
        with self.assertRaisesRegex(ValueError,'Output exists'):generate(self.run,dest)
        with patch('pathlib.Path.mkdir',side_effect=AssertionError('Import must not create folders')):
            importlib.reload(importlib.import_module('rq7_policy_sensitivity'))

    def test_incomplete_run_and_false_pareto_are_rejected(self):
        self.manifest['all_executed']=False;self.save()
        with self.assertRaisesRegex(ValueError,'incomplete'):generate(self.run,self.root/'bad')
        self.manifest['all_executed']=True
        self.grid[0].update(reached_round_limit=True,pareto_evaluable=False,pareto_nondominated=False)
        self.save()
        with self.assertRaisesRegex(ValueError,'Pareto status'):generate(self.run,self.root/'bad')

    def test_member_modules_share_production_implementations(self):
        from defi_models import analyses,simulation
        from defi_models.rq3 import rq3
        from defi_models.rq2_rq5 import rq2,rq5
        from defi_models.rq6 import rq6,cascade
        self.assertIs(analyses.rq3,rq3);self.assertIs(analyses.rq2,rq2);self.assertIs(analyses.rq5,rq5)
        self.assertIs(simulation.rq6,rq6);self.assertIs(simulation.cascade,cascade)

    def test_direct_files_offer_working_cli(self):
        root=Path(__file__).resolve().parents[1]
        for name in ('rq6','rq3','rq2_rq5'):
            command=subprocess.run([sys.executable,str(root/'defi_models'/f'{name}.py'),'--help'],cwd=self.root,capture_output=True,text=True)
            self.assertEqual(command.returncode,0,command.stderr)
            self.assertIn('--data-run',command.stdout)
