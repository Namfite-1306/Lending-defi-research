import io,json,tempfile,unittest,urllib.error
from pathlib import Path
from unittest.mock import patch,MagicMock
from defi_data.rpc import Rpc,RpcError,error_kind

class RpcResilienceTests(unittest.TestCase):
    def rpc(self,folder,urls=None):return Rpc(folder,urls=urls or ['https://first.example','https://second.example'])
    def response(self,obj):
        r=MagicMock();r.__enter__.return_value=io.StringIO(json.dumps(obj));return r
    def log(self,block=10):return {'address':'0xabc','topics':['topic'],'blockNumber':hex(block),'transactionHash':'tx','logIndex':'0x1','blockHash':'hash'}
    def test_pruned_falls_back_to_valid_provider(self):
        with tempfile.TemporaryDirectory() as d,patch('time.sleep'):
            r=self.rpc(d)
            with patch('urllib.request.urlopen',side_effect=[self.response({'error':{'code':4444,'message':'pruned history unavailable'}}),self.response({'result':[self.log()]})]):
                self.assertEqual(len(r.logs('0xabc',['topic'],10,10)),1)
    def test_range_limit_not_masked_by_pruned_fallback(self):
        with tempfile.TemporaryDirectory() as d,patch('time.sleep'):
            r=self.rpc(d)
            with patch('urllib.request.urlopen',side_effect=[self.response({'error':{'code':-32600,'message':'10 blocks range'}}),self.response({'error':{'code':4444,'message':'pruned history unavailable'}})]):
                self.assertEqual(error_kind(r._post({})['error']),'range_limit')
    def test_only_range_limit_bisects(self):
        with tempfile.TemporaryDirectory() as d:
            r=self.rpc(d);r.one=MagicMock(side_effect=[RpcError('10 blocks range'),[self.log(10)],[self.log(11)]])
            self.assertEqual(len(r.logs('0xabc',['topic'],10,11)),2)
            self.assertEqual(r.one.call_count,3)
    def test_pruned_auth_rate_and_unknown_never_bisect(self):
        with tempfile.TemporaryDirectory() as d:
            for message in ['4444 pruned history unavailable','HTTP 403','429 rate limit','execution reverted','network request failed']:
                r=self.rpc(d);r.one=MagicMock(side_effect=RpcError(message))
                with self.assertRaises(RpcError):r.logs('0xabc',['topic'],0,1000000)
                self.assertEqual(r.one.call_count,1)
    def test_duplicate_or_out_of_range_logs_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            for logs in [[self.log(),self.log()],[self.log(11)]]:
                r=self.rpc(d);r.one=MagicMock(return_value=logs)
                with self.assertRaises(RpcError):r.logs('0xabc',['topic'],10,10)
    def test_cached_empty_logs_are_not_used(self):
        with tempfile.TemporaryDirectory() as d:
            r=self.rpc(d);params=[{'address':'0xabc','topics':[['topic']],'fromBlock':'0xa','toBlock':'0xa'}]
            r._path('eth_getLogs',params).write_text('[]')
            with patch.object(r,'_post',return_value={'result':[self.log()]}):self.assertEqual(len(r.logs('0xabc',['topic'],10,10)),1)
    def test_batch_pruned_item_retries_individually(self):
        with tempfile.TemporaryDirectory() as d:
            r=self.rpc(d);r._post=MagicMock(side_effect=[[{'id':0,'error':{'code':4444,'message':'pruned'}}],{'result':'0x1234'}])
            self.assertEqual(r.many([('eth_call',[{},'0xa'])]),['0x1234'])
    def test_preflight_rejects_empty_known_history_and_hides_urls(self):
        with tempfile.TemporaryDirectory() as d:
            r=self.rpc(d,['https://provider.example/private-secret'])
            def fake(self,method,params,cache=True):
                if method=='eth_chainId':return '0x1'
                if method=='eth_getBlockByNumber':return {'number':params[0]}
                if method=='eth_getLogs':return []
                if method=='eth_getTransactionReceipt':return {'logs':[]}
            report=Path(d)/'rpc_preflight.json'
            with patch.object(Rpc,'one',new=fake),self.assertRaises(RpcError):r.preflight(21762265,21762300,report)
            result=json.loads(report.read_text());self.assertFalse(result['passed']);self.assertNotIn('private-secret',report.read_text())
    def test_preflight_filters_bad_provider(self):
        fixtures=json.loads((Path(__file__).resolve().parents[1]/'data/sources/rpc_history_probes.json').read_text());p=max((p for p in fixtures if p['block']<=21762265),key=lambda p:p['block'])
        log=dict(address=p['address'],blockNumber=hex(p['block']),logIndex=hex(p['log_index']),transactionHash=p['tx'],blockHash='0xknown')
        with tempfile.TemporaryDirectory() as d:
            r=self.rpc(d)
            def fake(self,method,params,cache=True):
                if 'first.example' in self.urls[0]:raise RpcError('4444 pruned')
                if method=='eth_chainId':return '0x1'
                if method=='eth_getBlockByNumber':return {'number':params[0]}
                if method=='eth_getLogs':return [log]
                if method=='eth_getTransactionReceipt':return {'logs':[log]}
                if method=='eth_call':return '0x'+f'{6:064x}'
            with patch.object(Rpc,'one',new=fake):r.preflight(21762265,21762300,Path(d)/'report.json',True)
            self.assertEqual(r.urls,['https://second.example'])
    def test_failed_chunk_never_creates_coverage(self):
        from defi_data.pipeline import connect,crawl
        with tempfile.TemporaryDirectory() as d:
            c=connect(Path(d)/'raw.sqlite');r=MagicMock();r.logs.side_effect=RpcError('4444 pruned')
            with self.assertRaises(RpcError):crawl(r,c,10,10,1)
            self.assertEqual(c.execute('SELECT count(*) FROM coverage').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT count(*) FROM logs').fetchone()[0],0);c.close()
    def test_completed_checkpoint_retained_after_later_failure(self):
        from defi_data.pipeline import connect,crawl
        with tempfile.TemporaryDirectory() as d:
            c=connect(Path(d)/'raw.sqlite');r=MagicMock();r.logs.side_effect=[[],RpcError('4444 pruned')];r.block.return_value={'hash':'0xhash'}
            with self.assertRaises(RpcError):crawl(r,c,10,10,1)
            self.assertEqual(c.execute('SELECT count(*) FROM coverage').fetchone()[0],1);c.close()
    def test_generic_quota_limit_is_not_assumed_block_range(self):
        self.assertNotEqual(error_kind('request limit exceeded'),'range_limit')
    def test_expansion_missing_pilot_stops_before_rpc(self):
        from defi_data import expansion
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch.object(expansion,'OUT',root/'processed'),patch.object(expansion,'PILOT',root/'missing_pilot'),patch.object(expansion,'Rpc') as network:
                with self.assertRaises(RpcError) as e:expansion.extended_window()
                self.assertEqual(e.exception.kind,'missing_input');network.assert_not_called()
                self.assertFalse(json.loads((root/'processed/extended_window_gate.json').read_text())['passed'])
    def test_multicall_pruned_does_not_bisect_wallet_calls(self):
        with tempfile.TemporaryDirectory() as d:
            r=self.rpc(d);r.multicall=True;r.one=MagicMock(side_effect=RpcError('4444 pruned'))
            calls=[('eth_call',[{'to':'0x'+'1'*40,'data':'0x1234'},'0xa'])]*4
            with self.assertRaises(RpcError):r.many(calls)
            self.assertEqual(r.one.call_count,1)
    def test_malformed_single_response_falls_back(self):
        with tempfile.TemporaryDirectory() as d,patch('time.sleep'):
            r=self.rpc(d)
            with patch('urllib.request.urlopen',side_effect=[self.response([]),self.response({'result':'0x1'})]):
                self.assertEqual(r.one('eth_chainId',[],cache=False),'0x1')

if __name__=='__main__':unittest.main()
