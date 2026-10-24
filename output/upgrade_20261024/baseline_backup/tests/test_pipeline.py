import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from defi_data.evm import keccak,topic,parse_events,decode_event,calldata,address_array
from defi_data.pipeline import ROOT,CONTRACTS,connect,stress,normalize

class EvmTests(unittest.TestCase):
    def setUp(self):
        self.tmp_root=ROOT/'data/test_tmp'
        self.tmp_root.mkdir(parents=True,exist_ok=True)
    def test_keccak_known_vectors(self):
        self.assertEqual(keccak(b'').hex(),'c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470')
        self.assertEqual(calldata('balanceOf(address)','0x'+'1'*40)[:10],'0x70a08231')
        self.assertEqual(topic('Transfer(address,address,uint256)'),
          '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef')
    def test_source_event_coverage(self):
        for _,source,names in CONTRACTS.values():
            specs=parse_events((ROOT/'data/sources'/source).read_text())
            for name in names: self.assertIn(name,specs)
        specs=parse_events((ROOT/'data/sources/IPool.sol').read_text())
        self.assertEqual(specs['Borrow']['signature'],'Borrow(address,address,address,uint256,uint8,uint256,uint16)')
    def test_liquidation_decode(self):
        spec=parse_events((ROOT/'data/sources/IPool.sol').read_text())['LiquidationCall']
        log={'topics':[spec['topic']]+['0x'+('0'*24)+str(i)*40 for i in (1,2,3)],
            'data':'0x'+f'{123:064x}{456:064x}'+('0'*24)+'4'*40+f'{1:064x}'}
        event=decode_event(log,spec)
        self.assertEqual(event['debtToCover'],123)
        self.assertEqual(event['liquidatedCollateralAmount'],456)
        self.assertEqual(event['liquidator'],'0x'+'4'*40)
        self.assertEqual(event['user'],'0x'+'3'*40)
    def test_morpho_id_not_address(self):
        spec=parse_events((ROOT/'data/sources/EventsLib.sol').read_text())['Liquidate']
        self.assertTrue(spec['signature'].startswith('Liquidate(bytes32,'))
    def test_sqlite_dedup(self):
        with tempfile.TemporaryDirectory(dir=self.tmp_root) as tmp:
            with closing(connect(Path(tmp)/'raw.sqlite')) as conn:
                row=(1,'tx',2,3,'hash','aave_v3','Borrow','{}','{}')
                for _ in range(2):conn.execute('INSERT OR REPLACE INTO logs VALUES (?,?,?,?,?,?,?,?,?)',row)
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM logs').fetchone()[0],1)
    def test_stress_shocks_both_debt_and_collateral(self):
        rows=[{'validation_status':'passed','account':'same_asset','symbol':'WETH',
            'price_usd':'100','supply_amount':'10','debt_amount':'7','collateral_enabled':True,'liquidation_threshold':'.8'}]
        with tempfile.TemporaryDirectory(dir=self.tmp_root) as tmp:
            stress(rows,Path(tmp))
            import csv
            with (Path(tmp)/'rq1_sample_stress.csv').open(encoding='utf-8-sig') as f:
                for row in csv.DictReader(f):self.assertEqual(row['accounts_at_risk'],'0')
    def test_failed_positions_excluded(self):
        with tempfile.TemporaryDirectory(dir=self.tmp_root) as tmp:
            stress([{'validation_status':'failed'}],Path(tmp))
            self.assertIn('sample_only_not_actual_liquidation_volume',(Path(tmp)/'rq1_sample_stress.csv').read_text(encoding='utf-8-sig'))
    def test_hourly_exposure_uses_requested_interval(self):
        class NoEventsRpc:
            def many(self,calls):return []
        import csv
        with tempfile.TemporaryDirectory(dir=self.tmp_root) as tmp:
            with closing(connect(Path(tmp)/'raw.sqlite')) as conn:
                normalize(NoEventsRpc(),conn,10,12,Path(tmp),0,10800)
            with (Path(tmp)/'hourly_counts.csv').open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),9)
            self.assertTrue(all(r['observed_seconds']=='3600' and r['partial_hour']=='False' for r in rows))
    def test_partial_hour_remains_explicit(self):
        class NoEventsRpc:
            def many(self,calls):return []
        import csv
        with tempfile.TemporaryDirectory(dir=self.tmp_root) as tmp:
            with closing(connect(Path(tmp)/'raw.sqlite')) as conn:
                normalize(NoEventsRpc(),conn,10,12,Path(tmp),1800,3600)
            with (Path(tmp)/'hourly_counts.csv').open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
            self.assertTrue(all(r['observed_seconds']=='1800' and r['partial_hour']=='True' for r in rows))

if __name__=='__main__':unittest.main()
