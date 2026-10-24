import io,json,tempfile,unittest,urllib.error
from unittest.mock import patch,MagicMock
from decimal import Decimal as D
from defi_data.recovery import merge_ranges,accrued_market,to_assets_up,WAD
from defi_data.multicall import word,encode_aggregate,decode_aggregate
from defi_data.evm import calldata
from defi_data.evm import parse_events,decode_event
from defi_data.expansion import protocol_hf,risk_debt_raw
from defi_data.rpc import Rpc,RpcError
from defi_data.pipeline import ROOT
from defi_data.recovery_recursive import motifs

class RecoveryTests(unittest.TestCase):
    def test_dynamic_configuration_label(self):
        s=parse_events('event Category(uint8 indexed id, uint16 lt, string label);')['Category']
        data=f'{9200:064x}{64:064x}{3:064x}'+b'ETH'.hex().ljust(64,'0')
        l={'topics':[s['topic'],'0x'+f'{2:064x}'],'data':'0x'+data}
        self.assertEqual(decode_event(l,s),{'id':2,'lt':9200,'label':'ETH'})
        l['data']=l['data'][:-64]
        with self.assertRaises(ValueError):decode_event(l,s)
    def test_binary_configuration_payload(self):
        s=parse_events('event Rate(address indexed asset, bytes data);')['Rate']
        l={'topics':[s['topic'],'0x'+'0'*24+'1'*40],'data':'0x'+f'{32:064x}{2:064x}'+'ff00'.ljust(64,'0')}
        self.assertEqual(decode_event(l,s)['data'],'0xff00')
    def test_union_coverage_not_sum(self):
        r=merge_ranges([(10,19),(0,9),(5,15),(30,39),(35,49)])
        self.assertEqual(r,[[0,19],[30,49]])
        self.assertEqual(sum(y-x+1 for x,y in r),40)
    def test_virtual_shares_and_rounding(self):
        self.assertEqual(to_assets_up(0,0,0),0)
        self.assertEqual(to_assets_up(1,0,0),1)
        self.assertEqual(to_assets_up(10**6,0,0),1)
        self.assertEqual(to_assets_up(1,100,10**6),1)
    def test_interest_matches_taylor_and_fee(self):
        state=[2000,2000*10**6,1000,1000*10**6,100,10**17]
        result=accrued_market(state,10**15,110)
        first=10**16;second=first*first//(2*WAD);third=second*first//(3*WAD)
        interest=1000*(first+second+third)//WAD
        self.assertEqual(result[2],1000+interest)
        self.assertEqual(result[0],2000+interest)
        self.assertEqual(result[3],state[3]);self.assertEqual(result[4],110)
        self.assertEqual(accrued_market(state,0,100),state)
        with self.assertRaises(ValueError):accrued_market(state,0,99)
    def test_negative_static_abi(self):
        self.assertEqual(calldata('tickBitmap(int16)',-1)[10:],'f'*64)
    def test_revision_specific_hf(self):
        self.assertEqual(protocol_hf(D(100),D('80.009'),D(50),D(10**8),8),D('1.6'))
        self.assertEqual(protocol_hf(D(100),D('80.009'),D(50),D(10**8),9),D('1.60018'))
    def test_risk_debt_uses_scaled_balance_not_discounted_balance(self):
        ray=10**27
        self.assertEqual(risk_debt_raw(0,1,ray+1,6),1)
        self.assertEqual(risk_debt_raw(0,1,ray+1,9),2)
        self.assertEqual(risk_debt_raw(7,10,2*ray,6),27)
    def test_multicall_dynamic_offsets(self):
        a=b'\x12\x34';t1=word(1)+word(64)+word(2)+a+b'\0'*30
        t2=word(0)+word(64)+word(0)
        encoded='0x'+(word(32)+word(2)+word(64)+word(64+len(t1))+t1+t2).hex()
        self.assertEqual(decode_aggregate(encoded),[(True,'0x1234'),(False,'0x')])
        self.assertEqual(encode_aggregate([{'to':'0x'+'1'*40,'data':'0x1234'}])[:10],'0x82ad56cb')
        with self.assertRaises(ValueError):decode_aggregate('0x00')
    def test_http_rpc_error_preserved(self):
        path=ROOT/'data/test_tmp';path.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=path) as tmp:
            r=Rpc(tmp,urls=['https://invalid.example'])
            error=urllib.error.HTTPError('url',400,'Bad request',{},io.BytesIO(json.dumps({'error':{'code':-32600,'message':'10 block range'}}).encode()))
            with patch('urllib.request.urlopen',side_effect=error):
                self.assertEqual(r._post({})['error']['code'],-32600)
            r.one=MagicMock(side_effect=RpcError('4444 pruned history unavailable'))
            with self.assertRaises(RpcError):r.logs('address',['topic'],0,100)
            self.assertEqual(r.one.call_count,1)
    def test_fast_motif_respects_order_and_censoring(self):
        es=[{'name':n,'token':t,'account':'a','tx':str(i),'idx':i,'stamp':s}
            for i,(n,t,s) in enumerate([('Borrow','B',0),('Supply','A',100),('Borrow','B',200)])]
        result=list(motifs(es,6,1000));self.assertEqual(len(result),1)
        self.assertTrue(result[0]['right_censored']);self.assertFalse(result[0]['verified_recursive'])
        self.assertEqual(list(motifs(es,0,1000)),[])
if __name__=='__main__':unittest.main()
