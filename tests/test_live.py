import tempfile,unittest,time,json,threading,urllib.request
from pathlib import Path
from unittest.mock import MagicMock
from defi_live.store import Store
from defi_live.collector import Collector
from defi_live.server import freshness,make_server
from defi_data.rpc import RpcError,Rpc

def h(n,prefix='h',parent=None):return {'number':n,'hash':prefix+str(n),'parent':parent or prefix+str(n-1),'stamp':1700000000+n*12}
def raw(hd):return {'number':hex(hd['number']),'hash':hd['hash'],'parentHash':hd['parent'],'timestamp':hex(hd['stamp'])}
def event(n=2):return {'tx':'tx'+str(n),'idx':1,'block':n,'hash':'h'+str(n),'protocol':'aave_v3','name':'Borrow','account':'wallet','token':'token','stamp':h(n)['stamp'],'decoded':{}}

class LiveTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def seed(self):self.store.initialize(h(1),{'chain_id':1});self.store.commit([h(2),h(3)],[event(2),event(3)])
    def test_atomic_invalid_log_does_not_advance_cursor(self):
        self.store.initialize(h(1),{})
        e=event(2);e['hash']='orphan'
        with self.assertRaises(ValueError):self.store.commit([h(2)],[e])
        self.assertEqual(self.store.meta('cursor'),1);self.assertIsNone(self.store.header(2));self.assertEqual(self.store.events(),[])
    def test_parent_chain_must_be_contiguous(self):
        self.store.initialize(h(1),{})
        with self.assertRaises(ValueError):self.store.commit([h(2,parent='other')],[])
        self.assertEqual(self.store.meta('cursor'),1)
    def test_reorg_removes_orphan_events_and_products(self):
        self.seed();self.store.publish('models',3,'h3',h(3)['stamp'],{'observed':True})
        self.store.rollback(1);self.assertEqual(self.store.meta('cursor'),1);self.assertEqual(self.store.events(),[]);self.assertIsNone(self.store.product('models'))
    def test_orphan_product_cannot_be_published(self):
        self.seed()
        with self.assertRaises(ValueError):self.store.publish('models',3,'wrong',h(3)['stamp'],{})
    def test_duplicate_events_rollback_whole_chunk(self):
        self.store.initialize(h(1),{})
        with self.assertRaises(Exception):self.store.commit([h(2)],[event(2),event(2)])
        self.assertEqual(self.store.meta('cursor'),1);self.assertEqual(self.store.events(),[])
    def test_source_age_not_request_time_controls_freshness(self):
        p={'source_stamp':100,'built_at':999}
        self.assertEqual(freshness(p,120,now=1000)['state'],'stale')
        self.assertEqual(freshness(None,120)['state'],'unavailable')
    def test_freshness_uses_chain_reference_when_host_clock_skewed(self):
        p={'source_stamp':1050,'built_at':999}
        result=freshness(p,120,now=1000,source_now=1100)
        self.assertEqual(result['source_age_seconds'],50);self.assertEqual(result['state'],'fresh')
    def test_canonicalize_finds_common_ancestor(self):
        self.seed();c=Collector(self.store)
        c.get_header=lambda n:h(n,'h') if n<=1 else h(n,'x',parent='h1' if n==2 else None)
        c.canonicalize();self.assertEqual(self.store.meta('cursor'),1)
    def test_deep_reorg_stops_without_rewinding(self):
        self.seed();c=Collector(self.store,reorg_depth=2);c.get_header=lambda n:h(n,'x')
        with self.assertRaises(RpcError):c.canonicalize()
        self.assertEqual(self.store.meta('cursor'),3)
    def test_failed_protocol_chunk_has_no_partial_coverage(self):
        c=Collector(self.store,lookback=3,chunk=3)
        rpc=MagicMock()
        def one(method,params,cache=True):
            if method=='eth_chainId':return '0x1'
            if method=='eth_blockNumber':return '0x7'
            return raw(h(int(params[0],16)))
        rpc.one.side_effect=one;rpc.many.side_effect=lambda calls:[one(m,p) for m,p in calls];rpc.logs.side_effect=[[],RpcError('rate limit')];c.rpc=rpc
        with self.assertRaises(RpcError):c.poll()
        self.assertEqual(self.store.meta('cursor'),2);self.assertEqual(self.store.events(),[])
    def test_live_no_cache_ignores_block_number_cache(self):
        r=Rpc(self.tmp.name,use_cache=False);r._path('eth_chainId',[]).write_text('"0x2"');r._post=MagicMock(return_value={'result':'0x1'})
        self.assertEqual(r.one('eth_chainId',[]),'0x1');self.assertEqual(r._post.call_count,1)
    def test_no_cache_batches_do_not_write_state_cache(self):
        r=Rpc(self.tmp.name,use_cache=False);r._post=MagicMock(return_value=[{'id':0,'result':'0x1'}])
        self.assertEqual(r.many([('eth_chainId',[])]),['0x1']);self.assertEqual(list(r.cache.glob('*.json')),[])
    def test_liquidation_counts_are_not_limited_by_recent_events_cap(self):
        self.store.initialize(h(1),{});es=[]
        for i in range(10):
            e=event(2);e.update(tx='tx'+str(i),idx=i,name='LiquidationCall');es.append(e)
        self.store.commit([h(2)],es)
        self.assertEqual(sum(self.store.liquidation_groups(0,h(2)['stamp'],'aave_v3').values()),10)
        self.assertEqual(len(self.store.events(limit=2)),2)
    def test_events_upper_bound_prevents_newer_block_leak(self):
        self.seed();es=self.store.events(until=h(2)['stamp']);self.assertEqual(len(es),1);self.assertEqual(es[0]['block'],2)
    def test_http_status_and_static_routes(self):
        model=MagicMock();model.online_analytics.return_value={'state':'warming_up'}
        server=make_server(self.store,model,'127.0.0.1',0,15,300);threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            base=f'http://127.0.0.1:{server.server_port}'
            with urllib.request.urlopen(base+'/api/status') as r:s=json.load(r)
            self.assertEqual(s['state'],'starting')
            with urllib.request.urlopen(base) as r:self.assertIn(b'DeFi Observatory',r.read())
            with urllib.request.urlopen(base+'/research') as r:self.assertIn(b'research.js',r.read())
            with urllib.request.urlopen(base+'/start') as r:self.assertIn(b'objective-5',r.read())
            with urllib.request.urlopen(base+'/ux.js') as r:self.assertIn(b'data-research-tab',r.read())
            with urllib.request.urlopen(base+'/ux.css') as r:self.assertIn(b'focus-visible',r.read())
            with urllib.request.urlopen(base+'/overview.js') as r:self.assertIn(b'/api/research',r.read())
            with urllib.request.urlopen(base+'/rq-guides.js') as r:self.assertIn(b'RQ_GUIDES',r.read())
            with urllib.request.urlopen(base+'/findings.js') as r:self.assertIn(b'ResearchFindings',r.read())
            with urllib.request.urlopen(base+'/api/deployment') as r:self.assertTrue(json.load(r)['whatif_enabled'])
            with urllib.request.urlopen(base+'/guide') as r:self.assertIn('H3'.encode('utf8'),r.read())
            model.research_results=Path(self.tmp.name)/'no-results'
            model.research_data=Path(self.tmp.name)/'no-data'
            with urllib.request.urlopen(base+'/api/research') as r:research=json.load(r)
            self.assertEqual(research['snapshots'],[])
            self.assertEqual(research['manifest']['status'],'research_worker_starting')
            self.assertEqual(research['repair']['concentration'],[])
            self.assertEqual(research['repair']['manifest'],{})
            self.assertEqual(research['source_stage']['manifest'],{})
        finally:server.shutdown();server.server_close()
    def test_source_failure_does_not_relabel_old_product_fresh(self):
        self.seed();self.store.publish('prices',3,'h3',h(3)['stamp'],{'prices':[]})
        self.store.set_meta('collector_status',{'state':'error','error_kind':'network'})
        model=MagicMock();server=make_server(self.store,model,'127.0.0.1',0,15,300);threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/api/prices') as r:p=json.load(r)
            self.assertEqual(p['freshness']['state'],'source_error')
        finally:server.shutdown();server.server_close()
    def test_cross_protocol_failure_is_unknown_not_zero(self):
        from defi_live.exposures import exposures
        r=MagicMock();r.one.side_effect=RpcError('RPC network request failed')
        positions=[{'account':'wallet','token':'token','collateral_usd':'20','debt_usd':'10'}]
        result=exposures(r,self.store,['wallet'],2,positions,'oracle')
        self.assertEqual(len(result['edges']),2);self.assertEqual(len(result['errors']),1)
        self.assertFalse(result['causal_contagion_estimated']);self.assertEqual(result['morpho_markets_checked'],0)

if __name__=='__main__':unittest.main()
