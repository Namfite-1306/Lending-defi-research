"""Interactive jobs must share the real engine, retain provenance and reject bad inputs."""
import json
import math
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import MagicMock
from defi_live.lab import ResearchLab,LabBusy
from defi_live.store import Store
from defi_live.server import make_server
from defi_models.core import Portfolio,DEFAULTS
from defi_models.rq6 import cascade


def fixture():
    cfg=dict(DEFAULTS)
    p=Portfolio([dict(account='wallet',token='eth',symbol='WETH',collateral_usd='10000',debt_usd='0',effective_lt='.8'),
                 dict(account='wallet',token='usdc',symbol='USDC',collateral_usd='0',debt_usd='6000',effective_lt='.8')],cfg)
    return p,{'block':123,'active_debt_wallets':1},cfg,{'mode':'historical_fixed'}


class ResearchLabTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name);self.lab=ResearchLab(self.store,MagicMock());self.lab.history=fixture()

    def calculate(self,**changes):
        request=self.lab.parameters(dict(source='historical',shock=.3,**changes))
        self.lab.jobs['job']={'state':'running'};self.lab.busy=True
        self.lab.calculate('job',request)
        return self.lab.job('job')

    def test_result_matches_shared_cascade_and_does_not_mutate_snapshot(self):
        p,scope,cfg,_=self.lab.history;before=p.c.copy()
        result=self.calculate(max_rounds=100)
        self.assertEqual(result['state'],'completed')
        expected,_=cascade(p,.3,dict(cfg,max_rounds=100,liquidity_depth_usd=1e8,close_factor=.5,liquidation_bonus=.05,impact_coefficient=.05,gas_usd=20.))
        self.assertEqual(result['result']['cascade'],expected)
        self.assertTrue((p.c==before).all())
        self.assertEqual(result['result']['provenance']['block'],123)
        self.assertFalse(self.lab.busy)

    def test_zero_impact_control_and_factor_selection_are_explicit(self):
        result=self.calculate(factor='btc')['result']
        self.assertEqual(result['stress']['eligible_wallets'],0)
        self.assertGreater(result['cascade']['repaid_usd'],0)
        self.assertEqual(result['control']['max_cumulative_price_impact'],0)
        self.assertIn('jointly',result['assumptions'])

    def test_invalid_inputs_rejected_before_job_creation(self):
        bad=[dict(shock=float('nan')),dict(gas_usd=float('inf')),dict(shock=True),dict(max_rounds=2.5),
             dict(shock=.9),dict(source='other'),dict(file='private'),dict(liquidity_depth_usd=0)]
        for changes in bad:
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.lab.submit(dict(source='historical',**{k:v for k,v in changes.items() if k!='source'}) if 'source' not in changes else changes)
        self.assertEqual(self.lab.jobs,{})

    def test_busy_worker_has_no_unbounded_queue(self):
        self.lab.busy=True
        with self.assertRaises(LabBusy):self.lab.submit({'source':'historical'})
        self.assertEqual(self.lab.jobs,{})

    def test_missing_live_positions_are_failure_not_zero_result(self):
        request=self.lab.parameters({'source':'live'})
        self.lab.jobs['job']={'state':'running'};self.lab.calculate('job',request)
        result=self.lab.job('job')
        self.assertEqual(result['state'],'failed');self.assertNotIn('result',result)
        self.assertFalse(self.lab.busy)

    def test_old_live_source_keeps_stale_and_error_labels(self):
        self.store.initialize({'number':1,'hash':'h1','parent':'h0','stamp':100},{})
        records=[dict(account='wallet',token='eth',symbol='WETH',collateral_usd='10000',debt_usd='0',effective_lt='.8'),
                 dict(account='wallet',token='usdc',symbol='USDC',collateral_usd='0',debt_usd='6000',effective_lt='.8')]
        self.store.publish('position_rows',1,'h1',100,{'positions':records})
        self.store.set_meta('head',{'stamp':1000,'observed_at':time.time()})
        request=self.lab.parameters({'source':'live'})
        self.lab.jobs['job']={'state':'running'};self.lab.calculate('job',request)
        result=self.lab.job('job')
        self.assertEqual(result['result']['provenance']['source_state'],'stale')
        self.assertGreaterEqual(result['result']['provenance']['source_age_seconds_at_calculation'],900)
        self.store.set_meta('collector_status',{'state':'error'})
        self.lab.jobs['job']={'state':'running'};self.lab.calculate('job',request)
        self.assertEqual(self.lab.job('job')['result']['provenance']['source_state'],'source_error')

    def test_http_lab_routes_and_post_guards(self):
        server=make_server(self.store,MagicMock(),'127.0.0.1',0,15,300)
        server.research_lab.history=fixture()
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        base=f'http://127.0.0.1:{server.server_port}'
        with urllib.request.urlopen(base+'/lab') as response:self.assertIn(b'Research Lab',response.read())
        with urllib.request.urlopen(base+'/api/lab/data') as response:self.assertEqual(json.load(response)['mode'],'historical_fixed')
        for headers,status in [({'Content-Type':'text/plain'},415),({'Content-Type':'application/json','Origin':'https://foreign.test'},403)]:
            request=urllib.request.Request(base+'/api/lab/simulate',b'{"source":"historical"}',headers)
            with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(request)
            self.assertEqual(caught.exception.code,status)
        request=urllib.request.Request(base+'/api/lab/simulate',b'{"source":"historical","shock":0.3}',{'Content-Type':'application/json'})
        with urllib.request.urlopen(request) as response:
            self.assertEqual(response.status,202);job=json.load(response)
        for _ in range(100):
            with urllib.request.urlopen(base+'/api/lab/job?id='+job['id']) as response:result=json.load(response)
            if result['state']!='running':break
            time.sleep(.01)
        self.assertEqual(result['state'],'completed')
