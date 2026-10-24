import json,tempfile,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
from decimal import Decimal as D
import numpy as np
from research_h124.h1 import quarters,State,aggregate_check
from research_h124.h1_analysis import run as analyze_h1
from research_h124.h2 import link_comet,Prices,normalized,sensitivity,ZERO,USDC,WETH
from research_h124.h4 import history,fit
from research_h124.h4_nb import nb_objective
from defi_models.core import concentration
from defi_data.rpc import RpcError

def encoded(values):return '0x'+''.join(format(v,'064x') for v in values)

class ResearchUpgradeTests(unittest.TestCase):
    def test_h1_worker_lock_prevents_concurrent_collectors_and_releases(self):
        from research_h124.common import worker_lock
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'collector.lock'
            with worker_lock(path):
                with self.assertRaises(RuntimeError):
                    with worker_lock(path):pass
            with worker_lock(path):pass
    def test_gho_risk_debt_changes_at_pool_revision_seven(self):
        from research_h124.h1 import historical_risk_debt,GHO
        self.assertEqual(historical_risk_debt(GHO,6,0,110,10**27,100),(110,110))
        self.assertEqual(historical_risk_debt(GHO,7,0,110,10**27,100),(100,110))
        self.assertEqual(historical_risk_debt(USDC,7,0,110,10**27,100),(110,110))
    def test_research_reader_reports_fresh_partial_scope_without_promoting_it(self):
        from defi_live.research import research_data
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=root/'data';results=root/'results'
            (data/'h1/2023Q1').mkdir(parents=True);results.mkdir()
            (data/'h1/quarter_plan.json').write_text(json.dumps([{'quarter':'2023Q1'}]))
            (data/'h1/2023Q1/scope.json').write_text(json.dumps({'quarter':'2023Q1','wallets_scanned':1,'full_snapshot_complete':False}))
            result=research_data(results,data)
            self.assertEqual(result['snapshots'][0]['wallets_scanned'],1)
            self.assertFalse(result['snapshots'][0]['full_snapshot_complete'])
            self.assertEqual(result['tables']['h1_curves'],[])
    def test_fifteen_quarter_cutoffs_are_exact_utc_boundaries(self):
        q=quarters();self.assertEqual(len(q),15);self.assertEqual(q[0][0],'2023Q1');self.assertEqual(q[-1][0],'2026Q3')
        self.assertEqual(q[0][1].isoformat(),'2023-04-01T00:00:00+00:00');self.assertEqual(q[-1][1].isoformat(),'2026-10-01T00:00:00+00:00')
    def test_partial_one_wallet_snapshot_never_enters_h1(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'input';(root/'2023Q1').mkdir(parents=True)
            (root/'quarter_plan.json').write_text(json.dumps([{'quarter':'2023Q1'}]))
            (root/'2023Q1/scope.json').write_text(json.dumps({'quarter':'2023Q1','full_snapshot_complete':False,'wallets_scanned':1,'historical_borrowers':2000}))
            self.assertEqual(analyze_h1(root,Path(tmp)/'out'),[])
            self.assertEqual(json.loads((Path(tmp)/'out/summary.json').read_text())['full_snapshots'],0)
    def test_gho_total_supply_uses_undiscounted_not_repayable_debt(self):
        token='0x40d16fc0246ad3160ccc09b8d0d3a2cd28ae6c2f';s=MagicMock();s.tokens=[token];s.provider='0x'+'1'*40;s.block=1
        s.rpc.many.side_effect=[[encoded([1,0,2])],[encoded([110])]]
        r=aggregate_check(s,[{'token':token,'repayable_debt_raw':'100','debt_raw':'110'}],1)[0]
        self.assertTrue(r['passed']);self.assertEqual(r['borrower_sum_raw'],'110');self.assertEqual(r['repayable_borrower_sum_raw'],'100')
    def test_emode_rpc_network_failure_does_not_become_legacy_category(self):
        s=State.__new__(State);s.categories={};s.revision=1;s.rpc=MagicMock();s.pool='0x'+'1'*40;s.block=1
        w=[format(x,'064x') for x in [32,9000,9300,10100,0,160,0]]
        with patch('research_h124.h1.call',side_effect=[w,RpcError('network timeout',kind='network')]):
            with self.assertRaises(RpcError):s.category(1)
        with patch('research_h124.h1.call',side_effect=[w,RpcError('execution reverted',kind='rpc_error')]):self.assertIsNone(s.category(1)['bitmap'])
    def test_comet_joins_multiple_collaterals_without_duplicating_debt(self):
        def event(idx,name,d):return dict(tx='tx',idx=idx,block=10,stamp=100,decoded=d,name=name)
        rs=[event(1,'AbsorbCollateral',{'borrower':'a','asset':'x','collateralAbsorbed':10,'usdValue':100}),
          event(2,'AbsorbCollateral',{'borrower':'a','asset':'y','collateralAbsorbed':20,'usdValue':200}),
          event(3,'AbsorbDebt',{'borrower':'a','basePaidOut':1000,'usdValue':100000}),
          event(4,'Transfer',{'from':ZERO,'to':'a','amount':100})]
        episodes,legs=link_comet(rs);self.assertEqual(len(episodes),1);self.assertEqual(len(legs),2)
        self.assertEqual(episodes[0]['debt_raw_upper_estimate'],'900');self.assertEqual(episodes[0]['collateral_legs'],2)
        self.assertEqual({r['episode'] for r in legs},{episodes[0]['episode']})
    def test_comet_nonadjacent_mint_requires_trace(self):
        rs=[dict(tx='tx',idx=1,block=10,stamp=100,name='AbsorbDebt',decoded={'borrower':'a','basePaidOut':1000,'usdValue':100000}),
          dict(tx='tx',idx=3,block=10,stamp=100,name='Transfer',decoded={'from':ZERO,'to':'a','amount':100})]
        with self.assertRaises(ValueError):link_comet(rs)
    def test_prior_block_price_excludes_same_block_and_future(self):
        p=Prices([{'feed':'USDC/USD','block':10,'stamp':100,'price_usd':'.9'},{'feed':'USDC/USD','block':11,'stamp':112,'price_usd':'1'}])
        self.assertEqual(p.get(USDC,11,112)[0],.9);self.assertEqual(p.get(USDC,10,100)[2],'missing_prior_block_price')
        self.assertIsNone(p.get('unknown',12,120)[0])
    def test_normalization_equal_and_single_wallet(self):
        self.assertAlmostEqual(normalized(concentration([1,1,1]))['hhi_normalized'],0)
        self.assertIsNone(normalized(concentration([1]))['hhi_normalized'])
    def test_count_usd_share_same_wallets_after_large_wallet_exclusion(self):
        episodes=[];legs=[]
        for i,(borrower,usd) in enumerate([('a',1),('a',1),('b',100)]):
            episodes.append(dict(episode=str(i),protocol='aave_v3',date='2024-05-01',borrower=borrower,debt_token=USDC,debt_price_age_seconds=1,debt_usd_upper=usd,debt_usd_lower=usd))
            legs.append(dict(episode=str(i),token=WETH))
        table,_=sensitivity(episodes,legs)
        target=[r for r in table if r['window']=='common_calendar_2024' and r['token']==WETH and r['protocol']=='aave_v3' and r['max_price_age']==3600 and r['drop']=='top1']
        self.assertEqual(len(target),2);self.assertEqual(target[0]['retained_wallets_sha256'],target[1]['retained_wallets_sha256'])
    def test_hawkes_recursion_uses_only_past_counts(self):
        a=history([1,2,3,4],.5,1/12);b=history([1,2,3,9999],.5,1/12)
        np.testing.assert_array_equal(a,b);self.assertEqual(a[0],0)
    def test_test_outcomes_do_not_enter_training_fit(self):
        rng=np.random.default_rng(4);X=np.ones((300,1));y=rng.poisson(.5,300).astype(float);mask=np.arange(300)<200
        a,_=fit(X,y,history(y,.5,1/12),mask,1/12,True)
        y[200:]=1000;b,_=fit(X,y,history(y,.5,1/12),mask,1/12,True);np.testing.assert_allclose(a,b,rtol=0,atol=1e-10)
    def test_negative_binomial_gradient(self):
        rng=np.random.default_rng(2);X=np.column_stack([np.ones(100),rng.normal(size=100)]);y=rng.poisson(1,100);g=rng.random(100);par=np.array([.2,-.1,.3,-.2])
        _,analytic=nb_objective(par,X,y,g,1/12,True);finite=[]
        for j in range(len(par)):
            delta=np.zeros(len(par));delta[j]=1e-6
            finite.append((nb_objective(par+delta,X,y,g,1/12,True)[0]-nb_objective(par-delta,X,y,g,1/12,True)[0])/2e-6)
        np.testing.assert_allclose(analytic,finite,rtol=1e-5,atol=1e-6)
if __name__=='__main__':unittest.main()
