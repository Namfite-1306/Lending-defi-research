"""Fresh audit requests use shared RPC fallback without accepting cached evidence."""
import hashlib
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from defi_data import audit_qa
from defi_data.evm import calldata,encode_arg,parse_events
from defi_data.pipeline import ROOT,CONTRACTS,connect,csv_write,normalize,save_json,stress,utc
from defi_data.rpc import Rpc,RpcError


class AuditTests(unittest.TestCase):
    def setUp(self):
        base=ROOT/'data/test_tmp';base.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=base)
        self.root=Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.account='0x'+'a'*40;self.token='0x'+'1'*40
        self.run=self.root/'data/runs/pilot';self.out=self.run/'processed'
        self.run.mkdir(parents=True)
        self.specs={p:parse_events((ROOT/'data/sources'/source).read_text(encoding='utf8'))
                    for p,(_,source,_) in CONTRACTS.items()}
        self.logs=[]
        names={'aave_v3':'LiquidationCall','compound_v3_usdc':'AbsorbDebt','morpho_blue':'Liquidate'}
        conn=connect(self.run/'raw.sqlite')
        for i,(protocol,name) in enumerate(names.items()):
            spec=self.specs[protocol][name]
            values={field:(self.token if typ=='address' else ('0x'+'1'*64 if typ=='bytes32' else 10**18))
                    for field,typ,indexed in spec['fields']}
            values.update(user=self.account,borrower=self.account,receiveAToken=False)
            log=dict(address=CONTRACTS[protocol][0],blockNumber=hex(11),blockHash='hash11',
                     transactionHash='tx'+str(i),transactionIndex=hex(i),logIndex=hex(i),
                     topics=[spec['topic']]+['0x'+encode_arg(values[field]) for field,typ,indexed in spec['fields'] if indexed],
                     data='0x'+''.join(encode_arg(values[field]) for field,typ,indexed in spec['fields'] if not indexed))
            self.logs.append(log)
            from defi_data.evm import decode_event
            conn.execute('INSERT INTO logs VALUES (?,?,?,?,?,?,?,?,?)',
                         (1,log['transactionHash'],i,11,'hash11',protocol,name,json.dumps(log),json.dumps(decode_event(log,spec))))
            conn.execute('INSERT INTO coverage VALUES (?,?,?,?,?)',(protocol,10,20,'hash10','hash20'))
        conn.commit()
        class Headers:
            def many(self,calls):return [{'timestamp':hex(1100),'hash':'hash11'} for _ in calls]
        normalize(Headers(),conn,10,20,self.out,1000,2000);conn.close()
        self.events=audit_qa.read(self.out/'events.csv')
        liqs=audit_qa.read(self.out/'liquidations.csv')
        valued=[{**liqs[0],'debt_price_usd':'2','debt_repaid_usd':'2'}]
        csv_write(self.out/'aave_liquidations_valued.csv',valued)
        csv_write(self.out/'aave_reserves.csv',[{'token_address':self.token,'decimals':18}])
        from defi_data.pipeline import concentration
        concentration(valued,self.out)
        positions=[dict(validation_status='passed',account=self.account,symbol='USDC',price_usd='2',
                        supply_amount='2',debt_amount='1',collateral_enabled=True,liquidation_threshold='.8')]
        csv_write(self.out/'positions.csv',positions);stress(positions,self.out)
        self.validations=[dict(account=self.account,hf_reported='1.6',debt_reported_usd='2')]
        csv_write(self.out/'position_validation.csv',self.validations)
        csv_write(self.out/'token_transfers_sample.csv',[])
        self.scope={'registry':{'pool':CONTRACTS['aave_v3'][0],'oracle':self.token},'block_number':9}
        save_json(self.out/'snapshot_scope.json',self.scope)
        self.manifest=dict(status='completed',start_block=10,end_block=20,
                           settings={'start':utc(1000),'end':utc(2000)},
                           outputs={str(p.relative_to(self.run)):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.out.glob('*.csv')},
                           source_hashes={source:hashlib.sha256((ROOT/'data/sources'/source).read_bytes()).hexdigest() for _,source,_ in CONTRACTS.values()})
        save_json(self.run/'manifest.json',self.manifest)

    def fake_rpc(self,fail_hf=False,chain='0x1',zero_debt=False):
        logs=self.logs
        class FreshRpc:
            def __init__(self,*args,**kwargs):self.urls=['endpoint'];self.requests=0;self.calls=[]
            def one(self,method,params,cache=True):
                self.requests+=1;self.calls.append((method,params,cache))
                if cache:raise AssertionError('Live audit must bypass cache')
                if method=='eth_chainId':return chain
                if method=='eth_getTransactionReceipt':return {'logs':[l for l in logs if l['transactionHash']==params[0]]}
                if method=='eth_getBlockByNumber':
                    n=int(params[0],16)
                    return {'timestamp':hex({9:990,10:1000,20:1990,21:2000}[n]),'hash':'hash'+str(n)}
                if method=='eth_call':
                    if fail_hf:raise RpcError('eth_call failed: endpoint #1: HTTP 400; endpoint #2: -32601 not whitelisted')
                    values=[0,0,0,0,0,2**256-1] if zero_debt else [400000000,200000000,0,8000,7500,1600000000000000000]
                    return '0x'+''.join(encode_arg(n) for n in values)
                raise AssertionError(method)
        return FreshRpc

    @staticmethod
    def cached(method,params):
        base=params[0]['data']==calldata('BASE_CURRENCY_UNIT()')
        return '0x'+encode_arg(10**8 if base else 2*10**8)

    def run_fixture(self,online,rpc_class):
        with patch.object(audit_qa,'ROOT',self.root),patch.object(audit_qa,'Rpc',rpc_class), \
             patch.object(audit_qa,'cached',side_effect=self.cached), \
             patch.object(audit_qa,'parse_events',side_effect=lambda source:parse_events(source)), \
             redirect_stdout(io.StringIO()):
            # The fixture root has no duplicated source tree; audit source reads
            # use a temporary copy of the tiny ABI definitions only.
            sources=self.root/'data/sources';sources.mkdir(exist_ok=True)
            for _,source,_ in CONTRACTS.values():
                (sources/source).write_bytes((ROOT/'data/sources'/source).read_bytes())
            return audit_qa.run_audit('pilot',online)

    def test_live_helper_ignores_cached_result_and_honors_environment(self):
        endpoint='https://offline.test/custom'
        params=[{'to':self.token,'data':'0x'},hex(9)]
        rpc=Rpc(self.root/'cache',urls=[endpoint]);path=rpc._path('eth_call',params)
        path.write_text(json.dumps('old_cached_value'),encoding='utf8')
        requests=[]
        def respond(request,**kwargs):
            requests.append(request.full_url)
            return io.BytesIO(json.dumps({'result':'fresh_value'}).encode())
        with patch('urllib.request.urlopen',side_effect=respond),patch('time.sleep'):
            self.assertEqual(audit_qa.live('eth_call',params,rpc),'fresh_value')
            with patch.object(audit_qa,'ROOT',self.root),patch.dict(os.environ,{'ETH_RPC_URLS':endpoint}):
                self.assertEqual(audit_qa.live('eth_call',params),'fresh_value')
        self.assertEqual(requests,[endpoint,endpoint])
        self.assertEqual(json.loads(path.read_text()),'old_cached_value')

    def test_offline_oracle_evidence_supports_legacy_and_transport_v2_caches(self):
        params=[{'to':self.token,'data':calldata('BASE_CURRENCY_UNIT()')},hex(11)]
        key=json.dumps(['eth_call',params],sort_keys=True,separators=(',',':')).encode()
        name=hashlib.sha256(key).hexdigest()+'.json'
        base=self.root/'data/rpc_cache';base.mkdir()
        (base/name).write_text(json.dumps('legacy_evidence'),encoding='utf8')
        with patch.object(audit_qa,'ROOT',self.root):
            self.assertEqual(audit_qa.cached('eth_call',params),'legacy_evidence')
            (base/'transport_v2').mkdir()
            (base/'transport_v2'/name).write_text(json.dumps('current_evidence'),encoding='utf8')
            self.assertEqual(audit_qa.cached('eth_call',params),'current_evidence')

    def test_live_audit_succeeds_with_shared_fresh_client(self):
        results=self.run_fixture(True,self.fake_rpc())
        self.assertTrue(results['all_executed_checks_passed'])
        self.assertEqual(len(results['checks']),15)
        self.assertEqual(results['audit_mode'],'live')
        self.assertTrue(results['live_rpc']['cache_bypassed'])
        self.assertNotIn('live_endpoints',results)

    def test_hf_rpc_failure_is_saved_as_failed_check_with_offline_results(self):
        results=self.run_fixture(True,self.fake_rpc(fail_hf=True))
        self.assertFalse(results['all_executed_checks_passed'])
        self.assertEqual(sum(row['passed'] for row in results['checks']),14)
        failed=results['checks'][-1]
        self.assertEqual(failed['check'],'fresh_rpc_snapshot_hf')
        self.assertEqual(failed['detail']['status'],'rpc_unavailable')
        self.assertIn('HTTP 400',failed['detail']['error'])
        saved=json.loads((self.run/'audit/audit_results.json').read_text(encoding='utf8'))
        self.assertFalse(saved['all_executed_checks_passed'])

    def test_wrong_chain_cannot_pass_fresh_checks(self):
        rpc=self.fake_rpc(chain='0x89')()
        checks=audit_qa.live_checks(rpc,self.manifest,self.scope,self.events,self.validations,self.specs)
        self.assertTrue(all(not check['passed'] for check in checks))
        self.assertEqual(rpc.requests,1)

    def test_zero_debt_hf_is_checked_without_parsing_empty_decimal(self):
        rpc=self.fake_rpc(zero_debt=True)()
        validations=[dict(account=self.account,hf_reported='',debt_reported_usd='0')]
        checks=audit_qa.live_checks(rpc,self.manifest,self.scope,self.events,validations,self.specs)
        self.assertTrue(checks[-1]['passed'])
        self.assertEqual(checks[-1]['detail'][0]['hf_fresh'],'undefined_zero_debt')

    def test_protocol_without_liquidations_does_not_crash_receipt_sampling(self):
        rpc=self.fake_rpc()()
        events=[e for e in self.events if e['protocol']=='aave_v3']
        checks=audit_qa.live_checks(rpc,self.manifest,self.scope,events,self.validations,self.specs)
        self.assertTrue(checks[0]['passed'])
        self.assertEqual(len(checks[0]['detail']['protocols_without_liquidations']),2)

    def test_offline_audit_does_not_construct_a_network_client(self):
        with patch.object(audit_qa,'live',side_effect=AssertionError('No fresh calls in offline mode')):
            results=self.run_fixture(False,lambda *a,**k: (_ for _ in ()).throw(AssertionError('No RPC client in offline mode')))
        self.assertTrue(results['all_executed_checks_passed'])
        self.assertEqual(len(results['checks']),12)

    def test_cli_returns_nonzero_when_checks_fail(self):
        with patch.object(audit_qa,'run_audit',return_value={'all_executed_checks_passed':False}):
            self.assertEqual(audit_qa.main(['--live']),1)
        with patch.object(audit_qa,'run_audit',return_value={'all_executed_checks_passed':True}):
            self.assertEqual(audit_qa.main([]),0)


if __name__=='__main__':unittest.main()
