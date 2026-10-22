"""Unit tests for Member 6 RQ7 Policy Sensitivity model.
"""
import unittest
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class TestRQ7PolicySensitivity(unittest.TestCase):
    def setUp(self):
        self.out_dir = ROOT / 'output/rq7'
        self.scenarios_file = self.out_dir / 'policy_scenarios.csv'
        self.results_file = self.out_dir / 'sensitivity_results.csv'

    def test_output_files_exist(self):
        self.assertTrue(self.scenarios_file.is_file(), "Missing policy_scenarios.csv")
        self.assertTrue(self.results_file.is_file(), "Missing sensitivity_results.csv")
        self.assertTrue((self.out_dir / 'RQ7_REPORT.md').is_file(), "Missing RQ7_REPORT.md")

    def test_policy_parameters_in_valid_range(self):
        with open(self.scenarios_file, encoding='utf-8-sig') as f:
            scenarios = list(csv.DictReader(f))
        for s in scenarios:
            cf = float(s['close_factor'])
            bonus = float(s['bonus'])
            lt = float(s['lt_shift'])
            self.assertTrue(0 < cf <= 1.0, f"Invalid Close Factor: {cf}")
            self.assertTrue(0 <= bonus < 1.0, f"Invalid Bonus: {bonus}")
            self.assertTrue(-1.0 < lt < 1.0, f"Invalid LT shift: {lt}")

    def test_nonnegative_financial_metrics(self):
        with open(self.results_file, encoding='utf-8-sig') as f:
            results = list(csv.DictReader(f))
        for r in results:
            self.assertGreaterEqual(float(r['debt_repaid_usd']), 0, "Repaid debt cannot be negative")
            self.assertGreaterEqual(float(r['borrower_collateral_seized_usd']), 0, "Seized collateral cannot be negative")
            self.assertGreaterEqual(float(r['protocol_shortfall_usd']), 0, "Shortfall cannot be negative")
            self.assertGreaterEqual(float(r['price_impact_pct']), 0, "Price impact cannot be negative")
            self.assertLess(float(r['price_impact_pct']), 100, "Price impact exceeds 100%")

    def test_reproducible_and_consistent_baseline(self):
        with open(self.results_file, encoding='utf-8-sig') as f:
            results = list(csv.DictReader(f))
        # Ensure every scenario has all 3 shock levels
        by_scenario = {}
        for r in results:
            by_scenario.setdefault(r['scenario_id'], []).append(r['shock_level'])
        for sc_id, shocks in by_scenario.items():
            self.assertEqual(sorted(shocks), ['10%', '20%', '30%'], f"Scenario {sc_id} missing shocks")

if __name__ == '__main__':
    unittest.main()
