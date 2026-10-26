import json,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import MagicMock
import numpy as np
from defi_live.store import Store
from defi_live.lab import ResearchLab
from defi_live.server import make_server,RequestWindow
from research_h124.robustness.h2_uncertainty import calendar_counts,sample_bootstrap
from research_h124.robustness.h3_calibration import calibrated
from research_h124.robustness.cascade_forward import fit_quotes
from research_h124.robustness.h1_basis import reprice
from defi_models.core import Portfolio,DEFAULTS

class RobustnessUpgradeTests(unittest.TestCase):
    def test_calendar_resampling_preserves_zero_event_days_and_same_paired_weights(self):
        a=calendar_counts(31,99,7);b=calendar_counts(31,99,7)
        self.assertTrue(np.array_equal(a,b));self.assertTrue(np.all(a.sum(axis=1)==31));self.assertGreater(np.unique(a[:,20]).size,1)
    def test_bootstrap_point_includes_observed_zero_weight_wallets(self):
        from datetime import date
        rows=[{'borrower':'a','date':'2024-02-01','debt_native_USDC':'10','market_debt_usd':'10'}, {'borrower':'b','date':'2024-02-01','debt_native_USDC':'0','market_debt_usd':'0'}]
        point,values,w=sample_bootstrap(rows,'market_USD',date(2024,2,1),3,np.ones((2,3),dtype=int))
        self.assertEqual(point['entities'],2);self.assertEqual(point['hhi_normalized'],1);self.assertEqual(values[0,0],1)
    def test_calibrated_hurdle_uses_both_probability_and_positive_mean(self):
        z=np.array([-1.,1.]);mu=np.array([2.,4.]);r=2.;p0=(1+mu/r)**(-r);den=1-p0
        p=1/(1+np.exp(-z));raw=(z,p,mu,r,p0,den,p*mu/den)
        new=calibrated(raw,[0,1,0,np.log(r)])
        np.testing.assert_allclose(new[-1],raw[-1],rtol=1e-8)
        self.assertTrue(np.all(new[-1]<new[2]/new[5]))
    def test_quote_fit_never_uses_eval_date_or_future(self):
        def q(day,move):return {'event_date':day,'bounded_curve_usable':'True','input_target_usd':'1000000','price_move_token1_per_token0':str(move),'token_in':'0x1','token_out':'0x2','fee_pips':'500'}
        _,pairs,_,dates=fit_quotes([q('2024-01-01',-.01),q('2025-01-01',-.9),q('2026-01-01',-.99)],'2025-01-01')
        self.assertEqual(dates,['2024-01-01']);self.assertAlmostEqual(pairs['0x1|0x2'],.01)
    def test_repricing_changes_both_sides_without_mutating_source(self):
        rows=[{'account':'a','token':'eth','symbol':'WETH','collateral_usd':'100','debt_usd':'50','repayable_debt_usd':'50','effective_lt':'.8','pool_revision':'1'}]
        p=Portfolio(rows,DEFAULTS);q=reprice(p,[.9]);self.assertEqual(p.c[0,0],100);self.assertEqual(q.c[0,0],90);self.assertEqual(q.d[0,0],45)
    def test_completed_job_survives_backend_instance_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp);store.put_job('job',{'id':'job','state':'completed','result':{'provenance':{'block':123}}},'old')
            lab=ResearchLab(Store(tmp),MagicMock());self.assertEqual(lab.job('job')['result']['provenance']['block'],123)
    def test_running_job_is_not_falsely_completed_after_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp);store.put_job('job',{'id':'job','state':'running'},'old')
            lab=ResearchLab(store,MagicMock());self.assertEqual(lab.job('job')['state'],'interrupted');self.assertEqual(store.get_job('job')[1]['state'],'running')
    def test_rate_window_expires_at_sixty_seconds(self):
        r=RequestWindow(2);self.assertTrue(r.allow('a',0));self.assertTrue(r.allow('a',1));self.assertFalse(r.allow('a',2));self.assertTrue(r.allow('a',60));self.assertTrue(r.allow('b',2))
    def test_optional_bearer_auth_protects_api_not_static_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            server=make_server(Store(tmp),MagicMock(),'127.0.0.1',0,15,300,api_token='test-only-token')
            threading.Thread(target=server.serve_forever,daemon=True).start();base=f'http://127.0.0.1:{server.server_port}'
            try:
                with self.assertRaises(urllib.error.HTTPError) as failure:urllib.request.urlopen(base+'/api/deployment')
                self.assertEqual(failure.exception.code,401)
                req=urllib.request.Request(base+'/api/deployment',headers={'Authorization':'Bearer test-only-token'})
                with urllib.request.urlopen(req) as response:self.assertTrue(json.load(response)['whatif_enabled'])
                with urllib.request.urlopen(base+'/research') as response:self.assertEqual(response.status,200)
            finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
