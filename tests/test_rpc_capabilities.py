"""Provider method refusals, historical calls and safe failure diagnostics."""
import io
import json
import os
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr,redirect_stdout
from pathlib import Path
from unittest.mock import patch

from defi_data import expansion
from defi_data.pipeline import ROOT
from defi_data.rpc import Rpc,RpcError


class RpcCapabilityTests(unittest.TestCase):
    def setUp(self):
        base=ROOT/'data/test_tmp';base.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=base)
        self.root=Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def test_defaults_use_general_state_providers_and_honor_custom_configuration(self):
        with patch.dict(os.environ,{},clear=True):
            rpc=Rpc(self.root/'default')
        self.assertNotIn('https://rpc.flashbots.net',rpc.urls)
        self.assertIn('https://eth.drpc.org',rpc.urls)
        with patch.dict(os.environ,{'ETH_RPC_URLS':' https://offline.test/a, ,https://offline.test/b,https://offline.test/a '}):
            self.assertEqual(Rpc(self.root/'custom').urls,['https://offline.test/a','https://offline.test/b'])
        with patch.dict(os.environ,{'ETH_RPC_URLS':' , '}):
            with self.assertRaisesRegex(RpcError,'ETH_RPC_URLS') as caught:Rpc(self.root/'empty')
            self.assertEqual(caught.exception.kind,'configuration')

    def test_denied_method_is_skipped_on_later_calls_but_other_methods_still_work(self):
        visited=[]
        def respond(request,**kwargs):
            payload=json.loads(request.data);visited.append((request.full_url,payload['method']))
            denied=request.full_url.endswith('/restricted') and payload['method']=='eth_call'
            result={'error':{'code':-32601,'message':'rpc method is not whitelisted'}} if denied else {'result':'0x01'}
            return io.BytesIO(json.dumps(result).encode())
        rpc=Rpc(self.root/'cache',urls=['https://offline.test/restricted','https://offline.test/archive'])
        with patch('urllib.request.urlopen',side_effect=respond),patch('time.sleep'):
            self.assertEqual(rpc.one('eth_call',[{},'0x14c1358'],cache=False),'0x01')
            self.assertEqual(rpc.one('eth_call',[{},'0x14c1359'],cache=False),'0x01')
            self.assertEqual(rpc.one('eth_chainId',[],cache=False),'0x01')
        self.assertEqual(visited.count(('https://offline.test/restricted','eth_call')),1)
        self.assertEqual(visited.count(('https://offline.test/archive','eth_call')),2)
        self.assertEqual(visited[-1],('https://offline.test/restricted','eth_chainId'))

    def test_network_failure_retries_even_when_last_endpoint_denies_method(self):
        primary_calls=0;restricted_calls=0
        def respond(request,**kwargs):
            nonlocal primary_calls,restricted_calls
            if request.full_url.endswith('/primary'):
                primary_calls+=1
                if primary_calls==1:raise urllib.error.URLError('temporary connection failure')
                return io.BytesIO(json.dumps({'result':'0x01'}).encode())
            restricted_calls+=1
            return io.BytesIO(json.dumps({'error':{'code':-32601,'message':'rpc method is not whitelisted'}}).encode())
        rpc=Rpc(self.root/'cache',urls=['https://offline.test/primary','https://offline.test/restricted'])
        with patch('urllib.request.urlopen',side_effect=respond),patch('time.sleep'):
            self.assertEqual(rpc.one('eth_call',[{},'0x10'],cache=False),'0x01')
        self.assertEqual(primary_calls,2);self.assertEqual(restricted_calls,1)

    def test_all_endpoint_errors_are_reported_without_urls_or_keys(self):
        primary='https://offline.test/primary?api_key=SENSITIVE'
        def respond(request,**kwargs):
            error=({'code':429,'message':'rate limit at '+primary} if request.full_url==primary
                   else {'code':-32601,'message':'rpc method is not whitelisted'})
            return io.BytesIO(json.dumps({'error':error}).encode())
        rpc=Rpc(self.root/'cache',urls=[primary,'https://offline.test/restricted'])
        with patch('urllib.request.urlopen',side_effect=respond),patch('time.sleep'):
            with self.assertRaises(RpcError) as caught:rpc.one('eth_call',[{},'0x10'])
        message=str(caught.exception)
        for expected in ('eth_call','endpoint #1','429','endpoint #2','-32601','ETH_RPC_URLS'):
            self.assertIn(expected,message)
        self.assertNotIn('SENSITIVE',message);self.assertNotIn('https://',message)
        self.assertEqual({r['endpoint'] for r in caught.exception.failures},{1,2})
        self.assertFalse(rpc._path('eth_call',[{},'0x10']).exists())

    def test_http_error_body_can_disable_only_the_denied_method(self):
        requests=[]
        def respond(request,**kwargs):
            requests.append(request.full_url)
            if request.full_url.endswith('/restricted'):
                body=io.BytesIO(json.dumps({'error':{'code':-32601,'message':'rpc method is not whitelisted'}}).encode())
                raise urllib.error.HTTPError(request.full_url,400,'Bad Request',{},body)
            return io.BytesIO(json.dumps({'result':'0x01'}).encode())
        rpc=Rpc(self.root/'cache',urls=['https://offline.test/restricted','https://offline.test/archive'])
        with patch('urllib.request.urlopen',side_effect=respond),patch('time.sleep'):
            rpc.one('eth_call',[{},'0x10'],cache=False)
            rpc.one('eth_call',[{},'0x11'],cache=False)
        self.assertEqual(requests.count('https://offline.test/restricted'),1)
        self.assertEqual(rpc.requests,3)

    def test_rejected_log_method_does_not_trigger_recursive_block_splitting(self):
        body={'error':{'code':-32601,'message':'rpc method is not whitelisted'}}
        rpc=Rpc(self.root/'cache',urls=['https://offline.test/restricted'])
        with patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(body).encode())) as post,patch('time.sleep'):
            with self.assertRaises(RpcError):rpc.logs('0x'+'1'*40,['topic'],1,1000000)
        post.assert_called_once()

    def test_error_kind_preserves_range_limit_despite_other_provider_diagnostics(self):
        rpc=Rpc(self.root/'cache',urls=['https://offline.test/range','https://offline.test/pruned'])
        response={'error':{'code':-32600,'message':'10 blocks range'},'_rpc_failures':[
            {'endpoint':1,'code':-32600,'message':'10 blocks range'},
            {'endpoint':2,'code':4444,'message':'pruned history unavailable'}]}
        with patch.object(rpc,'_post',return_value=response):
            with self.assertRaises(RpcError) as caught:rpc.one('eth_getLogs',[{}],cache=False)
        self.assertEqual(caught.exception.kind,'range_limit')
        self.assertEqual(len(caught.exception.failures),2)

    def test_batch_method_refusal_recovers_using_historical_state_provider(self):
        def respond(request,**kwargs):
            payload=json.loads(request.data)
            if isinstance(payload,list):
                return io.BytesIO(json.dumps([{'id':0,'error':{'code':-32601,'message':'rpc method is not whitelisted'}}]).encode())
            denied=request.full_url.endswith('/restricted')
            result={'error':{'code':-32601,'message':'rpc method is not whitelisted'}} if denied else {'result':'0x'+'0'*64}
            return io.BytesIO(json.dumps(result).encode())
        rpc=Rpc(self.root/'cache',urls=['https://offline.test/restricted','https://offline.test/archive'])
        params=[{'to':'0x'+'1'*40,'data':'0x5c416540'},hex(21762264)]
        with patch('urllib.request.urlopen',side_effect=respond),patch('time.sleep'):
            self.assertEqual(rpc.many([('eth_call',params)]),['0x'+'0'*64])

    def test_enrich_records_failed_preflight_without_scanning_wallets(self):
        class DeniedRpc:
            def __init__(self,*args,**kwargs):pass
            def one(self,method,*args,**kwargs):
                if method=='eth_chainId':return '0x1'
                raise RpcError('eth_call failed: endpoint #1: -32601 rpc method is not whitelisted')
            def logs(self,*args,**kwargs):raise AssertionError('Wallet scan must not run after failed preflight')
        with patch.object(expansion,'RUN',self.root),patch.object(expansion,'OUT',self.root/'processed'), \
             patch.object(expansion,'Rpc',DeniedRpc):
            with self.assertRaisesRegex(RpcError,'historical_rpc_check'):expansion.enrich()
        result=json.loads((self.root/'enrichment_status.json').read_text(encoding='utf8'))
        self.assertEqual(result['status'],'failed');self.assertEqual(result['phase'],'historical_rpc_check')
        self.assertFalse(result['full_history_ready'])

    def test_enrich_records_failed_wallet_call_without_substituting_mode_zero(self):
        class DeniedRpc:
            def __init__(self,*args,**kwargs):pass
            def one(self,method,*args,**kwargs):return '0x1' if method=='eth_chainId' else '0x'+'0'*64
            def preflight(self,*args,**kwargs):return {'passed':True}
            def logs(self,*args,**kwargs):return []
            def many(self,*args,**kwargs):raise RpcError('eth_call failed: endpoint #2: -32601 rpc method is not whitelisted')
        with patch.object(expansion,'RUN',self.root),patch.object(expansion,'OUT',self.root/'processed'), \
             patch.object(expansion,'Rpc',DeniedRpc),patch.object(expansion,'aave_positions') as positions:
            with self.assertRaisesRegex(RpcError,'wallet_emodes'):expansion.enrich()
        positions.assert_not_called()
        result=json.loads((self.root/'enrichment_status.json').read_text(encoding='utf8'))
        self.assertEqual(result['phase'],'wallet_emodes');self.assertEqual(result['status'],'failed')

    def test_cli_exits_with_actionable_error_instead_of_rpc_traceback(self):
        stderr=io.StringIO()
        with patch('sys.argv',['expansion','enrich']),patch.object(expansion,'RUN',self.root), \
             patch.object(expansion,'enrich',side_effect=RpcError('eth_call: check ETH_RPC_URLS')), \
             redirect_stderr(stderr),redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as result:expansion.main()
        self.assertEqual(result.exception.code,1)
        self.assertIn('RPC error: eth_call',stderr.getvalue())
        self.assertNotIn('Traceback',stderr.getvalue())


if __name__=='__main__':unittest.main()
