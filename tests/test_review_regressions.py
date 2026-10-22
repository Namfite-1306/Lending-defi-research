"""Offline regression cases from the October 2026 code review."""
import csv
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from defi_data import expansion, recovery, recovery_features, recovery_prices, recovery_trace_funding
from defi_data.evm import calldata, encode_arg, parse_events, topic
from defi_data.pipeline import ROOT, CONTRACTS, connect, csv_write, save_json, ts
from defi_data.price_history import BLOCK_END, build_price_index, price_before_event, price_at_time
from defi_data.rpc import Rpc, RpcError


def price_row(price,block,txidx,logidx,stamp=1000,available=None):
    return dict(feed='ETH/USD',price_usd=str(price),block=block,transaction_index=txidx,
                log_index=logidx,stamp=stamp,available_stamp=stamp if available is None else available,schema_version=2)


class TempTests(unittest.TestCase):
    def setUp(self):
        folder=ROOT/'data/test_tmp';folder.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=folder)
        self.root=Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)


class PriceTests(TempTests):
    def test_equal_timestamps_follow_execution_order_not_price(self):
        index=build_price_index([price_row(100,100,1,1),price_row(90,100,2,2)])['ETH/USD']
        self.assertEqual(price_before_event(index,100,3,3,1000)['price_usd'],'90')

    def test_later_transaction_and_later_log_cannot_price_an_event(self):
        index=build_price_index([price_row(80,99,1,1,900),price_row(90,100,5,8)])['ETH/USD']
        for txidx,logidx in [(1,1),(5,7),(5,8)]:
            with self.subTest(txidx=txidx,logidx=logidx):
                self.assertEqual(price_before_event(index,100,txidx,logidx,1000)['price_usd'],'80')
        self.assertEqual(price_before_event(index,100,5,9,1000)['price_usd'],'90')

    def test_block_end_seed_is_unavailable_to_events_in_that_block(self):
        index=build_price_index([price_row(80,99,1,1,900),price_row(90,100,BLOCK_END,BLOCK_END)])['ETH/USD']
        self.assertEqual(price_before_event(index,100,8,9,1000)['price_usd'],'80')
        self.assertEqual(price_before_event(index,101,0,1,1012)['price_usd'],'90')

    def test_phase_seed_keeps_source_age_and_waits_for_availability(self):
        index=build_price_index([price_row(100,120,BLOCK_END,BLOCK_END,1000,11000)])['ETH/USD']
        self.assertIsNone(price_at_time(index,10999))
        row=price_at_time(index,11000)
        self.assertEqual(11000-row['stamp'],10000)

    def test_legacy_price_csv_requires_rebuild(self):
        with self.assertRaisesRegex(ValueError,'rerun defi_data.recovery_prices'):
            build_price_index([{'feed':'ETH/USD','stamp':1000,'price_usd':'100'}])

    def test_feature_export_uses_only_prices_before_each_liquidation(self):
        out=self.root/'processed';out.mkdir()
        weth=recovery_trace_funding.WETH
        with patch.object(recovery,'RUN',self.root):
            conn=recovery.database()
            for txidx,idx in [(1,1),(6,6)]:
                decoded=dict(user='borrower',liquidator='liquidator',debtAsset=weth,
                             collateralAsset=weth,debtToCover=10**18)
                conn.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                             ('aave_v3',100,txidx,idx,'tx'+str(idx),'hash',1000,'LiquidationCall',
                              'borrower',weth,'market',json.dumps(decoded),b''))
            conn.commit();conn.close()
            conn=recovery.database()
            conn.execute('INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',('compound_v3_usdc',100,9,9,'foreign','hash',1000,'AbsorbDebt','other','token','market',json.dumps({'borrower':'other','absorber':'liquidator','basePaidOut':1}),b''))
            conn.commit();conn.close()
            save_json(self.root/'block_range.json',{'start_block':99,'end_block':100,'protocols':['aave_v3']})
            csv_write(out/'history_coverage.csv',[{'download_complete':True}])
            csv_write(out/'chainlink_price_updates.csv',[
                price_row(80,99,0,0,900),price_row(100,100,4,4),price_row(90,100,5,5)])

            class FeatureRpc:
                def __init__(self,*args,**kwargs):pass
                def one(self,*args,**kwargs):return '0x01'
                def block(self,*args):return {'timestamp':hex(900)}
                def many(self,calls,**kwargs):
                    if not calls:return []
                    return ['0x'+encode_arg(18),'0x'+b'WETH'.hex().ljust(64,'0')]

            def short_ts(value):
                return {'2023-01-27T00:00:00Z':0,'2026-10-01T00:00:00Z':3600}.get(value,ts(value))
            with patch.object(recovery_features,'RUN',self.root),patch.object(recovery_features,'OUT',out), \
                 patch.object(recovery_features,'Rpc',FeatureRpc),patch.object(recovery_features,'ts',short_ts),redirect_stdout(io.StringIO()):
                recovery_features.main()
        rows=expansion.read_csv(out/'liquidations_model_table.csv')
        self.assertEqual([r['reported_event_amount_market_usd'] for r in rows],['80','90'])
        self.assertEqual({r['protocol'] for r in expansion.read_csv(out/'liquidations_hourly_full_period.csv')},{'aave_v3'})
        self.assertEqual({r['protocol'] for r in expansion.read_csv(out/'event_counts_by_year.csv')},{'aave_v3'})
        self.assertEqual({r['protocol'] for r in expansion.read_csv(out/'wallet_protocol_activity.csv')},{'aave_v3'})

    def test_phase_export_does_not_refresh_an_old_quote(self):
        start=ts('2023-01-27T00:00:00Z');activation=start+3600
        save_json(self.root/'block_range.json',{'start_block':100,'end_block':200})
        out=self.root/'processed'

        class PriceRpc(Rpc):
            def logs(self,address,topics,lo,hi):return []
            def one(self,*args,**kwargs):return '0x'+b'ETH / USD'.hex().ljust(64,'0')
            def block(self,b):return {'timestamp':hex(start-1 if b==99 else activation)}
            def many(self,calls,**kwargs):return ['0x'+encode_arg('0x'+'1'*40) for _ in calls]

        def fake_call(rpc,to,sig,args,b):
            if sig=='decimals()':return [encode_arg(8)]
            if sig=='aggregator()':return [encode_arg('0x'+'1'*40)]
            if sig=='phaseId()':return [encode_arg(1 if b<120 else 2)]
            if sig=='latestRoundData()':
                updated=start-100 if b==99 else activation-10000
                return [encode_arg(n) for n in (1,100*10**8,updated,updated,1)]
            raise AssertionError(sig)

        def short_ts(value):
            return start+7200 if value=='2026-10-01T00:00:00Z' else ts(value)
        with patch.object(recovery_prices,'ROOT',self.root), \
             patch.object(recovery_prices,'RUN',self.root),patch.object(recovery_prices,'OUT',out), \
             patch.object(recovery_prices,'Rpc',PriceRpc),patch.object(recovery_prices,'call',side_effect=fake_call), \
             patch.object(recovery_prices,'FEEDS',{'ETH/USD':'proxy'}), \
             patch.object(recovery_prices,'ts',short_ts),redirect_stdout(io.StringIO()):
            recovery_prices.main()
        rows=expansion.read_csv(out/'market_prices_hourly_full_period.csv')
        self.assertEqual(rows[1]['age_seconds'],'10000')
        self.assertEqual(rows[1]['stale'],'True')
        self.assertNotEqual(rows[1]['source_update_utc'],rows[1]['source_available_utc'])


class RpcFallbackTests(TempTests):
    def test_partial_batch_failure_falls_back_without_repeating_successes(self):
        visited=[]
        def respond(request,**kwargs):
            payload=json.loads(request.data);visited.append((request.full_url,payload))
            if isinstance(payload,list):
                result=[{'id':0,'result':'0x01'},{'id':1,'error':{'code':4444,'message':'pruned history unavailable'}}]
            elif request.full_url.endswith('/pruned'):
                result={'id':1,'error':{'code':4444,'message':'pruned history unavailable'}}
            else:result={'id':1,'result':'0x02'}
            return io.BytesIO(json.dumps(result).encode())
        rpc=Rpc(self.root/'cache',urls=['https://offline.test/pruned','https://offline.test/archive'])
        calls=[('eth_call',[{'to':'a','data':str(n)},'0x10']) for n in range(2)]
        with patch('urllib.request.urlopen',side_effect=respond),patch('time.sleep'):
            self.assertEqual(rpc.many(calls),['0x01','0x02'])
        self.assertEqual(len(visited),3)
        self.assertEqual(visited[-1][0],'https://offline.test/archive')
        self.assertEqual(visited[-1][1]['params'],calls[1][1])
        self.assertEqual(json.loads(rpc._path(*calls[1]).read_text()),'0x02')

    def test_exhausted_fallback_never_caches_errors(self):
        def respond(request,**kwargs):
            payload=json.loads(request.data);error={'code':4444,'message':'pruned history unavailable'}
            result=[{'id':0,'error':error}] if isinstance(payload,list) else {'id':1,'error':error}
            return io.BytesIO(json.dumps(result).encode())
        rpc=Rpc(self.root/'cache',urls=['https://offline.test/pruned'])
        calls=[('eth_call',[{},'0x10'])]
        with patch('urllib.request.urlopen',side_effect=respond),patch('time.sleep'):
            self.assertIn('rpc_error',rpc.many(calls,allow_errors=True)[0])
            with self.assertRaises(RpcError):rpc.many(calls)
        self.assertFalse(rpc._path(*calls[0]).exists())

    def test_batch_rejection_falls_back_to_single_calls(self):
        def respond(request,**kwargs):
            payload=json.loads(request.data)
            result={'error':{'code':-32600,'message':'batches not supported'}} if isinstance(payload,list) else {'result':'0x00'}
            return io.BytesIO(json.dumps(result).encode())
        rpc=Rpc(self.root/'cache',urls=['https://offline.test/provider'])
        with patch('urllib.request.urlopen',side_effect=respond),patch('time.sleep'):
            self.assertEqual(rpc.many([('eth_call',[{},'0x10'])]),['0x00'])


class ExpansionGateTests(TempTests):
    def test_overlapping_checkpoints_are_unioned_and_clipped(self):
        save_json(self.root/'block_range.json',{'start_block':10,'end_block':19})
        conn=connect(self.root/'raw.sqlite')
        conn.executemany('INSERT INTO coverage VALUES (?,?,?,?,?)',
                         [('aave_v3',a,b,'h','h') for a,b in [(0,14),(10,19),(15,29)]])
        conn.commit();conn.close()
        with patch.object(expansion,'RUN',self.root),patch.object(expansion,'OUT',self.root/'processed'):
            expansion.export_history()
        rows=expansion.read_csv(self.root/'processed/history_coverage.csv')
        self.assertEqual(rows[0]['covered_blocks'],'10')
        self.assertEqual(rows[0]['coverage_fraction'],'1.0')
        self.assertEqual(rows[0]['verified_coverage_fraction'],'0')
        gaps=expansion.read_csv(self.root/'processed/history_gaps.csv')
        self.assertTrue(all(r['protocol']!='aave_v3' for r in gaps))

    def test_missing_pilot_invalidates_previous_success_without_rpc(self):
        out=self.root/'processed'
        save_json(out/'extended_window_gate.json',{'passed':True})
        with patch.object(expansion,'PILOT',self.root/'missing/processed'),patch.object(expansion,'OUT',out), \
             patch.object(expansion,'Rpc') as rpc:
            with self.assertRaises(RpcError):expansion.extended_window()
        self.assertFalse(json.loads((out/'extended_window_gate.json').read_text(encoding='utf8'))['passed'])
        rpc.assert_not_called()

    def pilot(self,empty=False):
        run=self.root/'pilot';out=run/'processed';out.mkdir(parents=True)
        conn=connect(run/'raw.sqlite')
        rows=[]
        if not empty:
            for i,name in enumerate(('Borrow','Supply')):
                rows.append(dict(chain_id=1,protocol='aave_v3',event_type=name,block_number=21,
                                 transaction_index=0,log_index=i,tx_hash='tx'))
                conn.execute('INSERT INTO logs VALUES (?,?,?,?,?,?,?,?,?)',(1,'tx',i,21,'h','aave_v3',name,'{}','{}'))
        conn.executemany('INSERT INTO coverage VALUES (?,?,?,?,?)',[(p,21,21,'h','h') for p in CONTRACTS])
        conn.commit();conn.close()
        csv_write(out/'events.csv',rows)
        save_json(run/'manifest.json',dict(status='completed',start_block=21,end_block=21,
                  settings={'start':'2025-02-03T00:00:00Z','end':'2025-02-03T03:00:00Z'},
                  outputs={'processed/events.csv':hashlib.sha256((out/'events.csv').read_bytes()).hexdigest()}))
        return out

    def test_empty_or_modified_pilot_is_not_a_valid_sentinel(self):
        pilot=self.pilot(empty=True);out=self.root/'processed'
        with patch.object(expansion,'PILOT',pilot),patch.object(expansion,'OUT',out), \
             patch.object(expansion,'Rpc') as rpc,redirect_stdout(io.StringIO()):
            with self.assertRaises(RpcError):expansion.extended_window()
            self.assertFalse(json.loads((out/'extended_window_gate.json').read_text(encoding='utf8'))['passed'])
            (pilot/'events.csv').write_text('modified',encoding='utf8')
            with self.assertRaises(RpcError):expansion.extended_window()
        rpc.assert_not_called()
        self.assertFalse(json.loads((out/'extended_window_gate.json').read_text(encoding='utf8'))['passed'])

    def test_valid_pilot_still_rejects_omitted_rpc_logs(self):
        pilot=self.pilot();out=self.root/'processed'
        class EmptyRpc:
            def __init__(self,*args,**kwargs):pass
            def one(self,*args,**kwargs):return hex(100)
            def block_at(self,*args):return 21
            def preflight(self,*args,**kwargs):return {'passed':True}
            def logs(self,*args):return []
        with patch.object(expansion,'PILOT',pilot),patch.object(expansion,'OUT',out), \
             patch.object(expansion,'Rpc',EmptyRpc),redirect_stdout(io.StringIO()):
            expansion.extended_window()
        gate=json.loads((out/'extended_window_gate.json').read_text(encoding='utf8'))
        self.assertFalse(gate['passed'])
        self.assertEqual(gate['missing_pilot_keys'],2)


    def test_verified_nonempty_pilot_and_matching_window_pass(self):
        pilot=self.pilot();out=self.root/'processed'
        specs=parse_events((ROOT/'data/sources/IPool.sol').read_text(encoding='utf8'))
        values=dict(reserve='0x'+'1'*40,user='0x'+'2'*40,onBehalfOf='0x'+'2'*40,
                    amount=1,interestRateMode=2,borrowRate=0,referralCode=0)
        logs=[]
        for i,name in enumerate(('Borrow','Supply')):
            spec=specs[name]
            logs.append(dict(address=CONTRACTS['aave_v3'][0],blockNumber=hex(21),blockHash='h',transactionHash='tx',
                transactionIndex='0x0',logIndex=hex(i),
                topics=[spec['topic']]+['0x'+encode_arg(values[n]) for n,t,indexed in spec['fields'] if indexed],
                data='0x'+''.join(encode_arg(values[n]) for n,t,indexed in spec['fields'] if not indexed)))
        class MatchingRpc:
            def __init__(self,*args,**kwargs):pass
            def one(self,*args,**kwargs):return hex(100)
            def block_at(self,stamp,*args):return 21 if stamp==ts('2025-02-01T00:00:00Z') else 22
            def preflight(self,*args,**kwargs):return {'passed':True}
            def logs(self,*args):return logs
            def many(self,calls):return [{'hash':'h','timestamp':hex(ts('2025-02-03T00:00:00Z'))} for _ in calls]
        with patch.object(expansion,'PILOT',pilot),patch.object(expansion,'OUT',out), \
             patch.object(expansion,'Rpc',MatchingRpc),redirect_stdout(io.StringIO()):
            expansion.extended_window()
        gate=json.loads((out/'extended_window_gate.json').read_text(encoding='utf8'))
        self.assertTrue(gate['passed']);self.assertEqual(gate['pilot_keys_reconciled'],2)
        self.assertEqual(gate['events'],2)


class TraceFundingTests(TempTests):
    def run_case(self,initial=0,unwrap=True,external=False,prior_verified=False,trace_error=False,reverted=False):
        account='0x'+'1'*40;collateral='0x'+'2'*40;converter='0x'+'3'*40;other='0x'+'4'*40
        pool=CONTRACTS['aave_v3'][0];weth=recovery_trace_funding.WETH;q=10**18;tx='0x'+'a'*64
        def node(to,data='0x',value=0,sender=account,children=None):
            return dict(type='CALL',to=to,**{'from':sender},input=data,value=hex(value),calls=children or [])
        borrow=node(pool,calldata('borrow(address,uint256,uint256,uint16,address)',weth,q,2,0,account))
        children=[borrow]
        if unwrap:
            withdrawal=node(weth,calldata('withdraw(uint256)',q),children=[node(account,value=q,sender=weth)])
            if reverted:withdrawal['error']='execution reverted'
            children.append(withdrawal)
        if external:children.append(node(account,value=q,sender=other))
        children.extend([node(converter,value=q,children=[node(collateral,calldata('mint(address,uint256)',account,q),sender=converter)]),
                         node(pool,calldata('supply(address,uint256,address,uint16)',collateral,q,account,0)),borrow])
        trace=node(account,sender=other,children=children)
        specs=parse_events((ROOT/'data/sources/IPool.sol').read_text(encoding='utf8'))
        def event(name,idx,**values):
            spec=specs[name]
            return dict(address=pool,logIndex=hex(idx),topics=[spec['topic']]+['0x'+encode_arg(values[n]) for n,t,indexed in spec['fields'] if indexed],
                        data='0x'+''.join(encode_arg(values[n]) for n,t,indexed in spec['fields'] if not indexed))
        def transfer(token,sender,receiver,idx):
            return dict(address=token,logIndex=hex(idx),topics=[topic('Transfer(address,address,uint256)'),
                        '0x'+encode_arg(sender),'0x'+encode_arg(receiver)],data='0x'+encode_arg(q))
        borrow_fields=dict(reserve=weth,user=account,onBehalfOf=account,amount=q,interestRateMode=2,borrowRate=0,referralCode=0)
        logs=[event('Borrow',1,**borrow_fields),transfer(weth,pool,account,2),transfer(collateral,'0x'+'0'*40,account,3),
              event('Supply',4,reserve=collateral,user=account,onBehalfOf=account,amount=q,referralCode=0),
              event('Borrow',5,**borrow_fields),transfer(weth,pool,account,6)]
        record=dict(tx=tx,account=account,block=100,status='verified_trace_funded_partial_collateral' if prior_verified else 'unresolved')
        if prior_verified:record['funded_collateral_raw']=str(q)
        out=self.root/'processed';csv_write(out/'recursive_receipt_verification.csv',[record])
        class TraceRpc:
            def __init__(self,*args,**kwargs):pass
            def one(self,*args,**kwargs):return {'transactionIndex':'0x0','logs':logs}
            def logs(self,*args,**kwargs):return []
        def traced(tx,tracer):
            if trace_error:raise RuntimeError('temporary RPC failure')
            return trace if tracer=='callTracer' else {account:{'balance':hex(initial)}}
        with patch.object(recovery_trace_funding,'RUN',self.root),patch.object(recovery_trace_funding,'OUT',out), \
             patch.object(recovery_trace_funding,'Rpc',TraceRpc),patch.object(recovery_trace_funding,'traced',side_effect=traced), \
             patch.object(recovery_trace_funding,'call',return_value=[encode_arg(0)]),redirect_stdout(io.StringIO()):
            recovery_trace_funding.main()
        return expansion.read_csv(out/'recursive_receipt_verification.csv')[0],json.loads((self.root/'trace_funding_evidence.json').read_text())

    def test_own_native_eth_cannot_prove_borrowed_funding(self):
        record,evidence=self.run_case(initial=10**18,unwrap=False)
        self.assertEqual(record['status'],'unresolved');self.assertEqual(evidence,[])

    def test_external_native_funding_without_unwrap_is_unresolved(self):
        record,evidence=self.run_case(unwrap=False,external=True)
        self.assertEqual(record['status'],'unresolved');self.assertEqual(evidence,[])

    def test_successful_unwrap_native_flow_and_mint_are_verified(self):
        record,evidence=self.run_case()
        self.assertEqual(record['status'],'verified_trace_funded_partial_collateral')
        self.assertEqual(record['funding_proof_version'],'2');self.assertEqual(len(evidence),1)
        self.assertIn('unwrap_call_index',evidence[0])

    def test_reverted_unwrap_is_not_funding(self):
        record,evidence=self.run_case(reverted=True)
        self.assertEqual(record['status'],'unresolved');self.assertEqual(evidence,[])

    def test_failed_revalidation_downgrades_old_trace_labels(self):
        record,evidence=self.run_case(prior_verified=True,trace_error=True)
        self.assertEqual(record['status'],'unresolved');self.assertEqual(evidence,[])
        self.assertNotIn('funded_collateral_raw',record)


if __name__=='__main__':unittest.main()
