import tempfile
import unittest
from pathlib import Path
from scripts.compare_model_runs import compare_runs
from defi_models.core import write_json, write_csv


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.a, self.b = [Path(self.temp.name)/x for x in ('a', 'b')]
        for p in (self.a, self.b):
            (p/'rq1').mkdir(parents=True)
            write_json(p/'manifest.json', {'all_executed': True, 'config': {'seed': 42},
                'models': [{'rq': 1, 'execution': 'completed'}], 'mode': 'research_run',
                'data_run': str(p), 'input_files': [], 'versions': {}})
            write_json(p/'rq1/summary.json', {'count': 1000000000, 'estimate': .123456})
            write_csv(p/'rq1/table.csv', [{'count': 1000000000, 'value': 1.2345}])

    def test_same_output_matches(self):
        self.assertTrue(compare_runs(self.a, self.b)['passed'])

    def test_float_tolerance_and_exact_large_counts(self):
        write_csv(self.b/'rq1/table.csv', [{'count': 1000000000, 'value': 1.23450001}])
        self.assertTrue(compare_runs(self.a, self.b)['passed'])
        write_csv(self.b/'rq1/table.csv', [{'count': 1000000001, 'value': 1.2345}])
        self.assertFalse(compare_runs(self.a, self.b)['passed'])

    def test_missing_result_is_a_failure(self):
        (self.b/'rq1/table.csv').unlink()
        self.assertFalse(compare_runs(self.a, self.b)['passed'])

    def test_changed_seed_and_estimate_are_detected(self):
        write_json(self.b/'rq1/summary.json', {'count': 1000000000, 'estimate': .223456})
        self.assertFalse(compare_runs(self.a, self.b)['passed'])
        manifest = __import__('json').loads((self.b/'manifest.json').read_text())
        manifest['config']['seed'] = 43
        write_json(self.b/'manifest.json', manifest)
        self.assertGreaterEqual(compare_runs(self.a, self.b)['difference_count'], 2)
