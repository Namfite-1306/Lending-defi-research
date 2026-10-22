import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock,call

from defi_data.recovery_prices import fetch_logs
from defi_data.rpc import RpcError


class PriceLogCollectionTests(unittest.TestCase):
    def test_bounds_requests_without_skipping_boundary_blocks(self):
        rpc=Mock()
        rpc.logs.side_effect=[['first'],[],['last']]
        with redirect_stdout(io.StringIO()):
            rows=fetch_logs(rpc,'address','topic',10,30,chunk_size=10)
        self.assertEqual(rows,['first','last'])
        self.assertEqual(rpc.logs.call_args_list,[
            call('address',['topic'],10,19),call('address',['topic'],20,29),call('address',['topic'],30,30)])

    def test_failed_chunk_does_not_become_an_empty_success(self):
        rpc=Mock()
        rpc.logs.side_effect=[['first'],RpcError('service temporarily unavailable',kind='network')]
        with redirect_stdout(io.StringIO()),self.assertRaises(RpcError):
            fetch_logs(rpc,'address','topic',10,30,chunk_size=10)
        self.assertEqual(rpc.logs.call_count,2)

    def test_suspected_capped_result_is_requeried_in_smaller_ranges(self):
        rpc=Mock()
        rpc.logs.side_effect=[['capped']*9500,['left'],['right']]
        with redirect_stdout(io.StringIO()):
            self.assertEqual(fetch_logs(rpc,'address','topic',10,19),['left','right'])
        self.assertEqual(rpc.logs.call_args_list[1:],[call('address',['topic'],10,14),call('address',['topic'],15,19)])
