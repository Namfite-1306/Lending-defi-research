import unittest
from defi_data.expansion import signed,window_candidates,protocol_hf
from decimal import Decimal as D
from defi_data.pipeline import ts

class ExpansionTests(unittest.TestCase):
    def events(self):
        return [dict(protocol='aave_v3',account='wallet',event_type=kind,block_number=i,
                     transaction_index=0,log_index=i,tx_hash=str(i),token_address=token,
                     timestamp_utc=f'2025-02-03T0{hour}:00:00Z')
                for i,(kind,token,hour) in enumerate([('Borrow','USDC',0),('Supply','WETH',1),('Borrow','USDC',2)],1)]
    def test_signed_swap_amount(self):
        self.assertEqual(signed(f'{(1<<256)-17:064x}'),-17)
        self.assertEqual(signed(f'{17:064x}'),17)
    def test_hf_uses_protocol_basis_point_rounding(self):
        self.assertEqual(protocol_hf(D(100),D('80.009'),D(50),D(10**8)),D('1.6'))
        self.assertIsNone(protocol_hf(D(100),D(80),D(0),D(10**8)))
    def test_censoring_and_label_availability(self):
        result=window_candidates(self.events(),6,ts('2025-02-03T03:00:00Z'))
        self.assertEqual(len(result),1)
        self.assertTrue(result[0]['right_censored'])
        self.assertEqual(result[0]['label_available_at'],'2025-02-03T02:00:00Z')
        self.assertFalse(result[0]['verified_recursive'])
    def test_uncensored_and_wrong_token(self):
        e=self.events()
        self.assertFalse(window_candidates(e,6,ts('2025-02-04T00:00:00Z'))[0]['right_censored'])
        e[-1]['token_address']='DAI'
        self.assertEqual(window_candidates(e,6,ts('2025-02-04T00:00:00Z')),[])
    def test_window_and_order(self):
        self.assertEqual(window_candidates(self.events(),1,ts('2025-02-04T00:00:00Z')),[])
        e=self.events();e[0]['event_type']='Supply';e[1]['event_type']='Borrow'
        self.assertEqual(window_candidates(e,6,ts('2025-02-04T00:00:00Z')),[])
    def test_no_cartesian_count_inflation(self):
        e=self.events();extra=dict(e[1]);extra['log_index']=20;e.insert(2,extra)
        self.assertEqual(len(window_candidates(e,6,ts('2025-02-04T00:00:00Z'))),1)
if __name__=='__main__':unittest.main()
