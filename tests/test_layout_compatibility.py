"""Public imports and CLI contracts must survive physical source moves."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]

class LayoutCompatibilityTests(unittest.TestCase):
    def test_existing_research_module_names_remain_loadable(self):
        names=['common','h1','h1_analysis','h2','market_prices','h4','h4_data',
               'hurdle_model','cascade','source_audit','source_analysis','runner_v2']
        for name in names:
            with self.subTest(module=name):
                spec=importlib.util.find_spec('research_h124.'+name)
                self.assertIsNotNone(spec)
                self.assertEqual(spec.name,'research_h124.'+name)
                self.assertTrue(Path(spec.origin).is_file())

    def test_canonical_root_and_provenance_include_grouped_sources(self):
        from research_h124 import source_files
        from research_h124.common import ROOT as research_root
        self.assertEqual(research_root,ROOT)
        paths=source_files()
        names=[p.name for p in paths]
        identifiers=[str(p.relative_to(ROOT/'research_h124')) for p in paths]
        self.assertEqual(len(identifiers),len(set(identifiers)),'Duplicate source identities')
        public=[p.stem for p in paths if p.parent.name in ('shared','positions','concentration','temporal','cascade_engine','reporting','orchestration')]
        self.assertEqual(len(public),len(set(public)),'Flat public module resolution must be unambiguous')
        self.assertIn('hurdle_model.py',names)
        self.assertIn('source_audit.py',names)

    def test_existing_module_CLIs_show_help_without_crawling(self):
        env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
        for module in ['research_h124.market_prices','research_h124.hurdle_model']:
            with self.subTest(module=module):
                r=subprocess.run([sys.executable,'-m',module,'--help'],cwd=ROOT,env=env,
                                 capture_output=True,text=True,timeout=20)
                self.assertEqual(r.returncode,0,r.stderr)
                self.assertIn('usage:',r.stdout)

    def test_existing_script_CLI_keeps_working(self):
        r=subprocess.run([sys.executable,str(ROOT/'scripts/validate_model_run.py'),'--help'],
                         cwd=ROOT,capture_output=True,text=True,timeout=20)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('run',r.stdout)

if __name__=='__main__':unittest.main()

