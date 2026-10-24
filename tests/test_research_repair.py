import unittest
import numpy as np
from scipy.optimize import check_grad
from research_h124.repair_h3 import link,objective,masks,bootstrap_dynamic
from research_h124.h4 import history
from research_h124.repair_h2 import freshness,bootstrap_days,weights

class RepairTests(unittest.TestCase):
    def test_softplus_is_positive_with_linear_tail_not_an_output_cap(self):
        p,_=link(np.array([-1000.,10.,100.]),'softplus')
        self.assertTrue((p>0).all());self.assertAlmostEqual(p[2],100,places=6);self.assertGreater(p[2],p[1]*9)
    def test_poisson_and_nb_gradients(self):
        rng=np.random.default_rng(1);X=np.c_[np.ones(40),rng.normal(size=(40,3))];y=rng.poisson(.3,40);g=rng.random(40)
        for kind in ['exp','softplus']:
          for family in ['poisson','nb']:
            for exc in [False,True]:
                p=np.r_[[0.,.1,-.2,.3],[.2] if exc else [],[-1.] if family=='nb' else []]
                f=lambda q:objective(q,X,y,g,kind,family,exc,.001)
                self.assertLess(check_grad(lambda q:f(q)[0],lambda q:f(q)[1],p),1e-5)
    def test_event_history_never_uses_current_or_future_counts(self):
        a=history([1,0,4,9],168,1/12);b=history([1,0,999,999],168,1/12)
        np.testing.assert_array_equal(a[:3],b[:3])
    def test_chronological_masks_do_not_overlap(self):
        from defi_models.core import stamp
        t=np.array([stamp(s+'T00:00:00Z') for s in ['2024-01-01','2024-06-01','2025-02-01','2025-08-01']])
        tr,va,te=masks(t,np.ones(4,dtype=bool));self.assertFalse((tr&va|va&te|tr&te).any());self.assertTrue(va[2]);self.assertTrue(te[3])
    def test_depeg_policy_is_stricter_without_a_peg_substitute(self):
        self.assertTrue(freshness(7200,.999,'feed_policy',False));self.assertFalse(freshness(7200,.999,'feed_policy',True))
        self.assertFalse(freshness(10,None,'feed_policy'));self.assertFalse(freshness(-1,1.,'one_day'))
    def test_native_units_do_not_require_USD_price(self):
        rows=[{'borrower':'a','debt_raw_upper_estimate':'2000000'}]
        self.assertEqual(weights(rows,'USDC_upper')['a'],2);self.assertEqual(weights(rows,'count')['a'],1)
    def test_single_entity_bootstrap_keeps_undefined_HHI_as_none(self):
        rows=[{'date':d,'borrower':'a','debt_raw_upper_estimate':'2000000'} for d in ['2024-01-01','2024-01-02']]
        self.assertIsNone(bootstrap_days(rows,'USDC_upper',9)['hhi_normalized_95'])
    def test_dynamic_bootstrap_resimulates_slow_state_and_resets_gaps(self):
        y=np.array([0,0,1,0,2,0,0,1,0,0,0,1.]);slow=history(y,168,1/12);fast=history(y,.5,1/12)
        X=np.c_[np.ones(len(y)),np.log1p(slow)];par=np.array([0.,.1,.2]);idx=np.r_[1:5,7:12]
        r=bootstrap_dynamic(y,X,fast,slow,idx,par,'softplus','poisson',True,.5,True,np.array([0.]),np.array([1.]),9)
        self.assertTrue(r['dynamic_slow_background_resimulated']);self.assertEqual(r['segments'],2);self.assertEqual(r['bins'],9)

if __name__=='__main__':unittest.main()
