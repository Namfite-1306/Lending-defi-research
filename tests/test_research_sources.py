import unittest
import numpy as np
from scipy.optimize import check_grad
from research_h124.hurdle_model import nb_positive,logistic,predictions,score,randomized_pit
from research_h124.activity_controls import lagged_sum
from research_h124.market_prices import parse_page,covered,intervals

class SourceTests(unittest.TestCase):
    def test_positive_NB_and_logistic_gradients(self):
        rng=np.random.default_rng(8);X=np.c_[np.ones(30),rng.normal(size=(30,2))];y=rng.poisson(3,30)+1;par=np.array([1.,.1,-.2,-.5])
        f=lambda p:nb_positive(p,X,y,.001)
        self.assertLess(check_grad(lambda p:f(p)[0],lambda p:f(p)[1],par),1e-5)
        f=lambda p:logistic(p,X,(y>3).astype(float),.001)
        self.assertLess(check_grad(lambda p:f(p)[0],lambda p:f(p)[1],par[:3]),1e-5)
    def test_hurdle_probability_normalizes_and_mean_has_no_cap(self):
        X=np.ones((1001,1));pr=predictions(X,(np.array([-1.]),np.array([2.,0.])))
        probability=np.exp(score(np.arange(1001.),pr))
        self.assertAlmostEqual(probability.sum(),1.,places=8);self.assertAlmostEqual(float(probability@np.arange(1001)),pr[-1][0],places=7)
    def test_PIT_includes_randomization_for_zero_and_positive_counts(self):
        X=np.ones((20,1));pr=predictions(X,(np.array([-1.]),np.array([2.,0.])))
        u=randomized_pit(np.r_[np.zeros(10),np.ones(10)],pr)
        self.assertTrue(((u>0)&(u<1)).all());self.assertTrue((u[:10]<1-pr[1][:10]).all());self.assertTrue((u[10:]>=1-pr[1][10:]).all())
    def test_activity_window_excludes_current_and_future(self):
        a=lagged_sum([1,2,3,4],2);b=lagged_sum([1,2,999,999],2)
        np.testing.assert_array_equal(a,[0,1,3,5]);np.testing.assert_array_equal(a[:3],b[:3])
    def test_market_parser_rejects_ignored_historical_since(self):
        payload={'error':[],'result':{'USDCUSD':[['1','1',90,'b','m','',1]],'last':'90000000000'}}
        with self.assertRaises(ValueError):parse_page(payload,'100000000000')
    def test_market_pair_and_coverage_are_not_assumed(self):
        self.assertFalse(covered([[100,200],[300,400]],190,310));self.assertTrue(covered([[100,200]],100,199))
        payload={'error':[],'result':{'USDCUSDT':[],'last':'1'}}
        with self.assertRaises(ValueError):parse_page(payload,'0')
    def test_market_latest_only_response_cannot_claim_old_history(self):
        payload={'error':[],'result':{'USDCUSD':[['1','1',99999,'b','m','',1]],'last':'99999000000000'}}
        with self.assertRaises(ValueError):parse_page(payload,'100000000000')
    def test_revised_primary_scope_ends_before_Q2_2026(self):
        from research_h124.next_common import PRIMARY_END,PRIMARY_END_UTC
        from datetime import datetime,timezone
        self.assertEqual(PRIMARY_END,int(datetime(2026,4,1,tzinfo=timezone.utc).timestamp()));self.assertTrue(PRIMARY_END_UTC.startswith('2026-04-01'))
    def test_quarantined_page_cannot_bridge_a_coverage_gap(self):
        import sqlite3
        c=sqlite3.connect(':memory:')
        c.execute('CREATE TABLE pages(since TEXT,start REAL,end REAL)')
        c.executemany('INSERT INTO pages VALUES (?,?,?)',[('good',100,200),('gap',190,900)])
        intervals(c)
        c.execute('INSERT INTO quarantined_pages VALUES (?,?)',('gap','unverified gap'))
        self.assertTrue(covered(intervals(c),110,190));self.assertFalse(covered(intervals(c),110,800));c.close()

if __name__=='__main__':unittest.main()
