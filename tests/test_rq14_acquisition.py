"""Scoped research audits must reject bad alignment and unrelated model use."""
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stdout

from defi_data import recovery,recovery_audit,recovery_features,recovery_positions
from defi_data.rpc import Rpc

try:
    from defi_models.__main__ import preflight
    from defi_models.core import DEFAULTS
    MODEL_DEPS=True
except ModuleNotFoundError:
    MODEL_DEPS=False


class ProviderConfigurationTests(unittest.TestCase):
    def test_smaller_chunks_reuse_previously_committed_larger_checkpoint(self):
        class HistoryRpc:
            urls=['https://offline.test/archive']
            def __init__(self,*args,**kwargs):pass
            def preflight(self,*args,**kwargs):return {'passed':True}
            def one(self,*args,**kwargs):raise AssertionError('Committed range must not be downloaded again')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'block_range.json').write_text(json.dumps({'start_block':17000000,'end_block':17049999,'protocols':['aave_v3']}))
            with patch.object(recovery,'RUN',root),patch.object(recovery,'OUT',root/'processed'),patch.object(recovery,'Rpc',HistoryRpc),redirect_stdout(io.StringIO()):
                c=recovery.database()
                c.execute('INSERT INTO ranges VALUES (?,?,?,?,?,?,?)',('aave_v3',17000000,17049999,0,'digest','h','h'))
                c.commit();c.close()
                recovery.full_history(workers=1,chunk=10000,protocols=['aave_v3'])
            with (root/'processed/history_coverage.csv').open(encoding='utf-8-sig',newline='') as f:coverage=list(csv.DictReader(f))
            self.assertEqual(coverage[0]['covered_blocks'],'50000')
            self.assertEqual(coverage[0]['download_complete'],'True')

    def test_export_does_not_certify_aave_borrowers_from_another_protocol_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'block_range.json').write_text(json.dumps({'start_block':10,'end_block':19,'protocols':['morpho_blue']}))
            with patch.object(recovery,'RUN',root),patch.object(recovery,'OUT',root/'processed'),redirect_stdout(io.StringIO()):
                c=recovery.database()
                c.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',('aave_v3',12,0,1,'tx','h',1,'Borrow','wallet','token','m','{}',b''))
                c.execute('INSERT INTO ranges VALUES (?,?,?,?,?,?,?)',('morpho_blue',10,19,0,'digest','h','h'))
                c.commit();c.close();recovery.export()
            with (root/'processed/borrower_universe.csv').open(encoding='utf-8-sig',newline='') as f:self.assertEqual(list(csv.DictReader(f)),[])

    def test_history_collects_and_exports_only_selected_protocol(self):
        class HistoryRpc:
            urls=['https://offline.test/archive']
            def __init__(self,*args,**kwargs):pass
            def preflight(self,*args,**kwargs):return {'passed':True}
            def one(self,*args,**kwargs):return []
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'block_range.json').write_text(json.dumps({'start_block':17000000,'end_block':17000002}))
            with patch.object(recovery,'RUN',root),patch.object(recovery,'OUT',root/'processed'),patch.object(recovery,'Rpc',HistoryRpc),redirect_stdout(io.StringIO()):
                recovery.full_history(workers=1,chunk=10,protocols=['aave_v3'])
            with (root/'processed/history_coverage.csv').open(encoding='utf-8-sig',newline='') as f:coverage=list(csv.DictReader(f))
            self.assertEqual([r['protocol'] for r in coverage],['aave_v3'])
            self.assertEqual(coverage[0]['download_complete'],'True')
            self.assertEqual(json.loads((root/'block_range.json').read_text())['protocols'],['aave_v3'])

    def test_feature_and_snapshot_use_the_configured_historical_provider(self):
        class SetupComplete(Exception):pass
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for module in [recovery_features,recovery_positions]:
                def factory(*args,**kwargs):
                    rpc=Rpc(*args,**kwargs)
                    self.assertEqual(rpc.urls,['https://offline.test/archive'])
                    raise SetupComplete
                with self.subTest(module=module.__name__),patch.dict('os.environ',{'ETH_RPC_URLS':'https://offline.test/archive'}),patch.object(module,'ROOT',root),patch.object(module,'RUN',root),patch.object(module,'OUT',root/'processed'),patch.object(module,'database'),patch.object(module,'Rpc',side_effect=factory):
                    with self.assertRaises(SetupComplete):module.main()


@unittest.skipUnless(MODEL_DEPS,'Install requirements-models.txt')
class ScopedAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.out=self.root/'processed';self.out.mkdir()
        self.hours=['2025-02-01T00:00:00+00:00','2025-02-01T01:00:00+00:00']
        (self.root/'block_range.json').write_text(json.dumps({'start_utc':self.hours[0],'end_exclusive_utc':'2025-02-01T02:00:00+00:00'}))
        for n,s in [(1,'structure'),(2,'onchain')]:
            (self.root/f'audit_{n}_{s}.json').write_text(json.dumps({'all_integrity_passed':True,'models':[4]}))
        self.prices=[dict(feed=f,timestamp_utc=h,price_usd='100',source_update_utc=h,source_available_utc=h,stale='False') for f in ['ETH/USD','BTC/USD'] for h in self.hours]
        self.events=[dict(protocol='aave_v3',timestamp_utc=self.hours[0],tx='tx1',logidx='1')]
        self.counts=[dict(protocol='aave_v3',hour_utc=h,protocol_deployed='True',liquidation_events=str(int(i==0))) for i,h in enumerate(self.hours)]

    def write(self,name,rows):
        with (self.out/name).open('w',encoding='utf8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)

    def audit(self,models=None):
        self.write('market_prices_hourly_full_period.csv',self.prices)
        self.write('liquidations_model_table.csv',self.events)
        self.write('liquidations_hourly_full_period.csv',self.counts)
        with patch.object(recovery_audit,'RUN',self.root),patch.object(recovery_audit,'OUT',self.out):
            recovery_audit.scoped_research_audit(models or [4])
        return json.loads((self.root/'audit_3_research.json').read_text())

    def test_rq4_audit_cannot_certify_unrelated_models(self):
        self.assertTrue(self.audit()['all_integrity_passed'])
        self.assertTrue(preflight(self.root,dict(DEFAULTS),[4])['passed'])
        result=preflight(self.root,dict(DEFAULTS),[2])
        self.assertFalse(result['passed'])
        self.assertTrue(any('does not cover' in e for e in result['errors']))

    def test_future_price_availability_is_rejected(self):
        self.prices[0]['source_available_utc']=self.hours[1]
        self.assertFalse(self.audit()['all_integrity_passed'])

    def test_duplicate_events_and_missing_hour_are_rejected(self):
        self.events*=2
        self.assertFalse(self.audit()['all_integrity_passed'])
        self.events=self.events[:1];self.counts=self.counts[:1]
        self.assertFalse(self.audit()['all_integrity_passed'])

    def test_rq1_requires_full_snapshot_and_matching_prior_audits(self):
        self.assertFalse(self.audit([1,4])['all_integrity_passed'])
        self.assertFalse(preflight(self.root,dict(DEFAULTS),[1])['passed'])
