import unittest,tempfile,json
from pathlib import Path
import numpy as np
from research_h124.h4_data import asof,header_row
from research_h124.cascade import repay_limit,no_dust_amount,simulate,parameters
from research_h124.h4_extended import feature_groups
from defi_models.core import Portfolio,DEFAULTS

class ResearchV2Tests(unittest.TestCase):
    def test_missing_residual_is_not_a_rejected_test(self):
        from research_h124.model_quality_v2 import assess
        r=assess({'model':'x','test_events':'100','expected_test_events':'100'}, {})
        self.assertIsNone(r['residual_pass_5pct']);self.assertEqual(r['status'],'requires_residual_diagnostics')
    def test_new_hypothesis_labels_do_not_renumber_time_or_source_paths(self):
        from research_h124.hypotheses import current_report_labels,LABELS
        s=current_report_labels('H1/H2/H4 | H2 Comet | H4 mô hình | test H2/2025; h4_prefix/')
        self.assertIn('H1/H2/H3',s);self.assertIn('H2 Comet',s)
        self.assertIn('H3 mô hình',s);self.assertIn('H2/2025',s);self.assertIn('h4_prefix/',s)
        self.assertEqual(LABELS['H2']['module'],'h2');self.assertEqual(LABELS['H3']['module'],'h4')
    def test_high_logscore_does_not_hide_gross_count_miscalibration(self):
        from research_h124.model_quality_v2 import assess
        row={'model':'nb','test_events':'100','expected_test_events':'100000'}
        r=assess(row,{'bootstrap_KS_p':.02,'bootstrap_acf_p':.56})
        self.assertEqual(r['expected_observed_ratio'],1000);self.assertTrue(r['gross_count_error_screen'])
        self.assertFalse(r['deployment_ready']);self.assertEqual(r['status'],'requires_recalibration')
    def test_verified_prefix_stops_at_first_gap_even_if_later_headers_exist(self):
        from research_h124.h4_data import verified_prefix
        raw=[{'block':str(b)} for b in [10,11,12,13]]
        headers={10:(10,1001),11:(11,1601),13:(13,2201)}
        rows,verified,end,gap=verified_prefix(raw,headers)
        self.assertEqual([r['block'] for r in rows],['10','11'])
        self.assertEqual(set(verified),{10,11});self.assertEqual(end,1500);self.assertEqual(gap,12)
    def test_verified_prefix_rejects_empty_or_unneeded_scope(self):
        from research_h124.h4_data import verified_prefix
        with self.assertRaises(ValueError):verified_prefix([{'block':'10'}],{})
        with self.assertRaises(ValueError):verified_prefix([{'block':'10'}],{10:(10,1001)})
    def test_multicall_batches_preserve_each_historical_block(self):
        from unittest.mock import MagicMock,patch
        from research_h124.h4_utilization import aggregates
        rpc=MagicMock();rpc.many.return_value=['raw10','raw20'];word=lambda n:'0x'+format(n,'064x')
        with patch('research_h124.h4_utilization.decode_aggregate',side_effect=[[(True,word(1))],[(True,word(2))]]):
            result=aggregates(rpc,[(10,[('0x'+'1'*40,'balanceOf(address)',['0x'+'2'*40])]),(20,[('0x'+'1'*40,'balanceOf(address)',['0x'+'2'*40])])])
        calls=rpc.many.call_args.args[0];self.assertEqual([r[1][1] for r in calls],['0xa','0x14']);self.assertEqual(int(result[1][0][0],16),2)
    def test_revision_eight_uses_virtual_balance_even_if_legacy_flag_is_zero(self):
        from unittest.mock import MagicMock,patch
        from research_h124.h4_utilization import fetch_chunk
        word=lambda n:format(n,'064x')
        meta=[[[word(1)],[word(8)],[word(0)],[word(0)]]]
        def reserve(debt):return [word(x) for x in [0,0,0,0,debt,0,5*10**25,0,0,0,0,0]]
        state=[[reserve(200),[word(800)],reserve(40),[word(160)]]]
        with patch('research_h124.h4_utilization.Rpc',return_value=MagicMock()),patch('research_h124.h4_utilization.aggregates',side_effect=[meta,state]) as calls:
            rows=fetch_chunk([10])
        self.assertEqual(len(rows),2);self.assertAlmostEqual(rows[0][4],.2);self.assertEqual(rows[0][-1],1)
        methods=[r[1] for r in calls.call_args_list[1].args[1][0][1]];self.assertIn('getVirtualUnderlyingBalance(address)',methods)
    def test_residual_acf_does_not_join_isolated_bins_across_gaps(self):
        from research_h124.residual_v2 import segmented_acf
        self.assertIsNone(segmented_acf(np.array([.1,.9,.1,.9]),[1,1,1,1]))
        self.assertIsNotNone(segmented_acf(np.array([.1,.9,.1,.9]),[4]))
    def test_panel_build_respects_block_availability_and_upgrade_boundary(self):
        import sqlite3
        from unittest.mock import patch
        from research_h124.h4_data import build
        with tempfile.TemporaryDirectory() as tmp:
            data=Path(tmp)/'data';out=Path(tmp)/'results';data.mkdir();out.mkdir()
            (data/'pool_upgrades.json').write_text(json.dumps({'complete':True,'events':[{'stamp':0,'revision':1},{'stamp':3600,'revision':7}]}))
            c=sqlite3.connect(':memory:');c.execute('CREATE TABLE headers(block INTEGER,stamp INTEGER,hash TEXT,parent TEXT,base_fee TEXT,gas_used INTEGER,gas_limit INTEGER)')
            c.executemany('INSERT INTO headers VALUES (?,?,?,?,?,?,?)',[(1,0,'h1','h0','1000000000',1,2),(2,3600,'h2','h1','3000000000',1,2)])
            rows=[{'feed':f,'block':'1','round_id':'1','stamp':'0','price_usd':'100' if f in ['ETH/USD','BTC/USD'] else '1'} for f in ['ETH/USD','BTC/USD','USDC/USD','USDT/USD','DAI/USD']]
            rows.append({'feed':'ETH/USD','block':'2','round_id':'2','stamp':'3600','price_usd':'90'})
            from research_h124.common import write
            write(data/'processed/chainlink_price_updates.csv',rows)
            panel=(np.array([3600,3900,4200]),np.array([0,1,0]),np.zeros((3,8)),np.ones(3,dtype=bool),{})
            with patch('research_h124.h4.panel',return_value=panel),patch('research_h124.h4_data.oracle_rows',return_value=rows),patch('research_h124.h4_data.block_connection',return_value=c),patch('research_h124.h4_data.DATA',data),patch('research_h124.h4_data.OUT',out),patch('research_h124.h4_data.SOURCE',data):
                result=build()
            saved=np.load(data/'h4_panel_5min.npz');names=saved['names'].tolist();X=saved['X']
            self.assertEqual(X[0,names.index('ETH_oracle_down_5m')],0)
            self.assertGreater(X[1,names.index('ETH_oracle_down_5m')],0)
            self.assertEqual(X[0,names.index('pool_revision_7')],0)
            self.assertEqual(X[1,names.index('pool_revision_7')],1)
            self.assertEqual(result['status'],'completed_scoped')
            saved.close()
    def test_atomic_publish_retries_windows_sharing_violation(self):
        from unittest.mock import patch
        from research_h124.common import atomic_replace
        with patch('pathlib.Path.replace',side_effect=[PermissionError('sharing violation'),None]) as replace,patch('research_h124.common.time.sleep'):
            atomic_replace('tmp','dest');self.assertEqual(replace.call_count,2)
    def test_same_boundary_or_future_oracle_update_not_visible(self):
        values,idx=asof(np.array([10,11,20]),[10,20],[100,999])
        self.assertTrue(np.isnan(values[0]));self.assertEqual(values[1],100);self.assertEqual(values[2],100)
    def test_changing_future_data_does_not_change_past_features(self):
        a,_=asof(np.array([11,15,20]),[10,20],[100,200]);b,_=asof(np.array([11,15,20]),[10,20],[100,99999])
        np.testing.assert_array_equal(a,b)
    def test_missing_series_stays_nan(self):
        values,_=asof(np.array([10,20]),[],[]);self.assertTrue(np.isnan(values).all())
    def test_unsorted_availability_rejected(self):
        with self.assertRaises(ValueError):asof(np.array([10]),[20,10],[1,2])
    def test_wrong_block_response_rejected(self):
        with self.assertRaises(ValueError):header_row({'number':'0x2'},1)
    def test_invalid_gas_fields_rejected(self):
        with self.assertRaises(ValueError):header_row(dict(number='0x2',timestamp='0x10',hash='h',parentHash='p',baseFeePerGas='0x1',gasUsed='0xa',gasLimit='0x9'))
    def test_revision_six_applies_close_factor_to_selected_debt(self):
        self.assertEqual(repay_limit(6,.97,10000,3000,5000),1500)
    def test_revision_seven_applies_half_total_debt_limit(self):
        self.assertEqual(repay_limit(7,.97,10000,3000,5000),3000)
        self.assertEqual(repay_limit(7,.97,10000,8000,9000),5000)
    def test_small_position_or_low_hf_allows_full_debt(self):
        self.assertEqual(repay_limit(7,.97,10000,1500,5000),1500)
        self.assertEqual(repay_limit(7,.95,10000,8000,9000),8000)
    def test_unknown_revision_rejected(self):
        with self.assertRaises(ValueError):repay_limit(99,.9,100,100,200)
    def test_dust_constraint_reduces_partial_proposal(self):
        amount=no_dust_amount(7,1500,2000,3000,.05)
        self.assertEqual(amount,1000);self.assertGreaterEqual(2000-amount,1000)
        self.assertGreaterEqual(3000-amount*1.05,1000)
    def test_partial_snapshot_cannot_enter_cascade(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'scope.json').write_text(json.dumps({'full_snapshot_complete':False}))
            with self.assertRaises(ValueError):parameters(root)
    def example(self,enabled=True):
        p=Portfolio([dict(account='a',token='c',symbol='WETH',collateral_usd=1000,debt_usd=0,repayable_debt_usd=0,effective_lt=.8,pool_revision=6),
          dict(account='a',token='d',symbol='USDC',collateral_usd=0,debt_usd=900,repayable_debt_usd=900,effective_lt=0,pool_revision=6)],DEFAULTS)
        params={'revision':6,'bonus':{'c':.05,'d':.05},'fees':{'c':.1,'d':0},'enabled':{'c':enabled,'d':True},'emode_bonus':{}}
        return p,params
    def test_conservation_and_protocol_fee(self):
        p,params=self.example();summary,rounds,actions=simulate(p,params,[{'ETH':1.,'BTC':1.}],{'c':0.},feedback=False,gas_usd=0)
        self.assertEqual(len(actions),1);a=actions[0];self.assertAlmostEqual(a['received_collateral_usd']+a['protocol_fee_usd'],a['seized_usd'])
        self.assertAlmostEqual(a['repaid_usd'],a['repayable_decrement_base_usd']);self.assertFalse(summary['historically_calibrated'])
    def test_unknown_liquidity_route_is_excluded_not_zero_impact(self):
        p,params=self.example();summary,rounds,actions=simulate(p,params,[{'ETH':1.,'BTC':1.}],{},gas_usd=0)
        self.assertEqual(actions,[]);self.assertEqual(rounds[0]['unsupported_route_wallets'],1)
    def test_paused_collateral_is_excluded(self):
        p,params=self.example(False);summary,rounds,actions=simulate(p,params,[{'ETH':1.,'BTC':1.}],{'c':0.},gas_usd=0)
        self.assertEqual(actions,[])
    def test_measured_collateral_without_debt_route_is_excluded(self):
        p,params=self.example();params['routes']={'c|c':0.}
        summary,rounds,actions=simulate(p,params,[{'ETH':1.,'BTC':1.}],{'c':0.},gas_usd=0)
        self.assertEqual(actions,[]);self.assertEqual(rounds[0]['unsupported_route_wallets'],1)
    def test_measured_pair_impact_can_be_used_without_token_proxy(self):
        p,params=self.example();params['routes']={'c|d':.0005};params['pair_impact']={'c|d':0.}
        summary,rounds,actions=simulate(p,params,[{'ETH':1.,'BTC':1.}],{},gas_usd=0)
        self.assertEqual(len(actions),1)
    def test_ablations_keep_gas_out_of_oracle_only_group(self):
        g=feature_groups(['ETH_oracle_down_5m','sampled_base_fee_log_gwei','USDC_positive_depeg','pool_revision_7','hour_sin'])
        self.assertEqual(g['oracle'],[0,4]);self.assertNotIn(1,g['oracle']);self.assertIn(1,g['oracle_gas'])
    def test_cascade_api_rejects_unlisted_directory(self):
        from defi_live.research import cascade_result
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):cascade_result(Path(tmp)/'results/old',Path(tmp)/'data/old','../../secret',.2,True)
if __name__=='__main__':unittest.main()
