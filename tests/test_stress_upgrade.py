import tempfile,time,unittest,json,urllib.request,threading
from pathlib import Path
from unittest.mock import MagicMock
from defi_live.store import Store
from defi_live.universe import UniverseScanner
from defi_live.server import make_server
from defi_models.core import Portfolio,DEFAULTS
from defi_models.pair_cascade import pair_cascade
from defi_models.stress_validation import QuoteCurve,temporal_concentration
from defi_data.event_snapshots import borrowers_before


class UpgradeTests(unittest.TestCase):
    def test_legacy_close_factor_at_threshold_uses_full_selected_debt(self):
        p=Portfolio([dict(account='a',token='c',symbol='WETH',collateral_usd=1000,debt_usd=0,effective_lt=.95,pool_revision=6),
          dict(account='a',token='d',symbol='USDC',collateral_usd=0,debt_usd=1000,effective_lt=0,pool_revision=6)],DEFAULTS)
        _,_,actions=pair_cascade(p,0,dict(DEFAULTS,max_rounds=1,impact_coefficient=0,gas_usd=0))
        self.assertEqual(actions[0]['close_factor'],1.)
    def test_pre_event_cohort_excludes_future_borrowers(self):
        self.assertEqual(borrowers_before([{'account':'a','first_borrow_block':'10'},{'account':'b','first_borrow_block':'20'}],15),['a'])
    def test_incomplete_historical_snapshot_cannot_be_exported_as_full(self):
        from defi_data.event_snapshots import export_completed
        with self.assertRaises(ValueError):export_completed(None,None,{'full_snapshot_complete':False,'passed':1,'active_debt_wallets':1})
    def test_borrow_discovery_backfill_closes_only_its_gap(self):
        from defi_live.universe import discovery_loop
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp);store.initialize(dict(number=1020,hash='h1020',parent='h1019',stamp=1000),{})
            store.set_meta('universe_seed',{'end_block':1000,'history_complete':True})
            scanner=UniverseScanner(store,MagicMock());stop=threading.Event();rpc=MagicMock()
            rpc.one.return_value={'hash':'canonical'};rpc.logs.return_value=[{}]
            stop.wait=MagicMock(side_effect=lambda _:stop.set())
            with patch('defi_data.rpc.Rpc',return_value=rpc),patch('defi_data.evm.decode_event',return_value={'onBehalfOf':'0x'+'1'*40}):discovery_loop(scanner,stop)
            self.assertEqual(store.meta('discovery_progress')['next_block'],1021)
            self.assertTrue(scanner.status()['discovery_gap_closed'])
            self.assertEqual(scanner.status()['known_wallets'],1)
            self.assertFalse(scanner.status()['full_market_coverage'])
    def test_poor_interpolation_is_not_silently_used(self):
        rows=[dict(pool='p',block=10,token_in='a',token_out='b',input_target_usd=x,cost_vs_spot_including_fee=c) for x,c in [(1000,.01),(10000,.1),(100000,.5)]]
        curve=QuoteCurve(rows)
        with self.assertRaises(ValueError):curve.proceeds(5000,10,'a','b')
        self.assertEqual(curve.proceeds(10000,10,'a','b'),9000)
    def test_failed_live_quotes_preserve_previous_product(self):
        from defi_live.liquidity import LiveLiquidity
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp);store.initialize(dict(number=1,hash='h1',parent='h0',stamp=1),{})
            store.publish('liquidity',1,'h1',1,{'quotes':['prior']});worker=LiveLiquidity(store)
            with patch('defi_live.liquidity.pool_quotes',side_effect=ValueError('offline')):
                with self.assertRaises(ValueError):worker.update()
            self.assertEqual(store.product('liquidity')['payload']['quotes'],['prior'])
    def test_curve_rejects_wrong_block_direction_and_extrapolation(self):
        rows=[dict(pool='p',block=10,token_in='a',token_out='b',input_target_usd=x,cost_vs_spot_including_fee=.01+x/1e6) for x in [1000,10000,100000]]
        c=QuoteCurve(rows)
        self.assertAlmostEqual(c.proceeds(1000,10,'a','b'),989)
        for args in [(999,10,'a','b'),(100001,10,'a','b'),(1000,11,'a','b'),(1000,10,'b','a')]:
            with self.assertRaises(ValueError):c.proceeds(*args)
    def test_common_priced_sample_and_stale_price_filter(self):
        rows=[dict(protocol='aave_v3',timestamp_utc='2025-01-01T00:00:00+00:00',borrower=a,collateral_token='t',reported_event_amount_market_usd=v,price_age_seconds=age) for a,v,age in [('a','100','20'),('b','','20'),('c','1000','7200')]]
        out=temporal_concentration(rows)
        self.assertTrue(all(r['priced_events']==1 and r['all_events']==3 for r in out))
        self.assertTrue(all(r['top10']==1 for r in out))
    def test_missing_usd_not_zero_concentration(self):
        rows=[dict(protocol='a',timestamp_utc='2025-01-01T00:00:00+00:00',borrower='a',collateral_token='t',reported_event_amount_market_usd='',price_age_seconds='')]
        self.assertTrue(all(r['hhi'] is None for r in temporal_concentration(rows) if r['metric']!='count_all'))
    def test_pair_repays_one_reserve_not_proportional_basket(self):
        rows=[dict(account='a',token='c',symbol='WETH',collateral_usd=1000,debt_usd=0,effective_lt=.8,pool_revision=6),
              dict(account='a',token='d',symbol='USDC',collateral_usd=0,debt_usd=900,effective_lt=0,pool_revision=6),
              dict(account='a',token='e',symbol='DAI',collateral_usd=0,debt_usd=10,effective_lt=0,pool_revision=6)]
        p=Portfolio(rows,DEFAULTS);original=p.d.copy();cfg=dict(DEFAULTS,max_rounds=1,impact_coefficient=0,gas_usd=0)
        r,h,actions=pair_cascade(p,0,cfg)
        self.assertEqual(len(actions),1);self.assertEqual(actions[0]['debt_token'],'d')
        self.assertEqual(actions[0]['close_factor'],1);self.assertAlmostEqual(actions[0]['repaid_usd'],900)
        self.assertAlmostEqual(actions[0]['seized_usd'],945);self.assertTrue((p.d==original).all())
        _,_,with_fee=pair_cascade(p,0,dict(cfg,protocol_fee_by_token={'c':.1}))
        self.assertAlmostEqual(with_fee[0]['protocol_fee_collateral_usd'],4.5)
        self.assertAlmostEqual(with_fee[0]['received_collateral_usd']+with_fee[0]['protocol_fee_collateral_usd'],with_fee[0]['seized_usd'])
        with self.assertRaises(ValueError):
            for row in rows:row['pool_revision']=11
            pair_cascade(Portfolio(rows,DEFAULTS),0,cfg)
    def test_census_persists_rotates_and_invalidates_reorg(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp);stamp=int(time.time())
            h=lambda n:dict(number=n,hash='h'+str(n),parent='h'+str(n-1),stamp=stamp+n)
            store.initialize(h(1),{});store.commit([h(2)],[])
            seed=Path(tmp)/'seed.csv';seed.write_text('account\n0x'+'1'*40+'\n0x'+'2'*40+'\n')
            rpc=MagicMock();rpc.one.return_value={'hash':'h2'}
            values=[0,100*10**8,0,0,0,2*10**18];rpc.many.return_value=['0x'+''.join(format(v,'064x') for v in values)]
            scan=UniverseScanner(store,rpc,seed,batch_size=1);scan.scan();first=scan.selected(1)
            scan.scan();self.assertEqual(scan.status()['scanned_wallets'],2)
            self.assertEqual(UniverseScanner(store,rpc,seed,1).status()['scanned_wallets'],2)
            self.assertEqual(len(first),1);store.rollback(1);self.assertEqual(scan.status()['scanned_wallets'],0)
    def test_failed_census_batch_does_not_advance_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp);store.initialize(dict(number=1,hash='h1',parent='h0',stamp=1),{})
            seed=Path(tmp)/'seed.csv';seed.write_text('account\n0x'+'1'*40+'\n')
            rpc=MagicMock();rpc.many.side_effect=ValueError('offline');scan=UniverseScanner(store,rpc,seed,1)
            with self.assertRaises(ValueError):scan.scan()
            self.assertEqual(scan.status()['scanned_wallets'],0)
    def test_evidence_http_and_missing_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp);models=MagicMock();models.evidence_dir=None;models.universe=None
            server=make_server(store,models,'127.0.0.1',0,15,300)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                root='http://127.0.0.1:'+str(server.server_port)
                with urllib.request.urlopen(root+'/validation') as r:self.assertEqual(r.status,200)
                with urllib.request.urlopen(root+'/api/universe') as r:self.assertEqual(json.load(r)['state'],'disabled')
                with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(root+'/api/validation')
                self.assertEqual(error.exception.code,503)
            finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
