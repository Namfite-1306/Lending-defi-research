import argparse,threading,time
from pathlib import Path
from .store import Store
from .collector import Collector,collector_loop
from .models import LiveModels,model_loop,exposure_loop
from .server import make_server
from defi_models.core import ROOT

def main():
    p=argparse.ArgumentParser(description='Local real-time monitoring dashboard. No signing or trades.')
    p.add_argument('--state-dir',type=Path,default=ROOT/'data/live/mainnet')
    p.add_argument('--port',type=int,default=8787);p.add_argument('--poll-seconds',type=float,default=15)
    p.add_argument('--snapshot-seconds',type=float,default=300);p.add_argument('--confirmations',type=int,default=2)
    p.add_argument('--lookback-blocks',type=int,default=120);p.add_argument('--chunk',type=int,default=30)
    p.add_argument('--start-block',type=int);p.add_argument('--wallet-limit',type=int,default=10);p.add_argument('--wallet-file',type=Path)
    p.add_argument('--historical-results',type=Path,default=ROOT/'results/review_20261022_full')
    p.add_argument('--once',action='store_true',help='One real collection + price + model pass; no server')
    p.add_argument('--universe-seed',type=Path,help='Audited historical borrower_universe.csv; enables persistent rolling census')
    p.add_argument('--universe-batch',type=int,default=200)
    p.add_argument('--universe-seconds',type=float,default=30)
    p.add_argument('--evidence-dir',type=Path,help='Output of defi_models.stress_validation, served read-only')
    p.add_argument('--liquidity-seconds',type=float,default=900)
    p.add_argument('--backtest-dir',type=Path,default=ROOT/'data/stress_backtests_20261024')
    p.add_argument('--research-results',type=Path,default=ROOT/'results/research_h124_20261024')
    p.add_argument('--research-data',type=Path,default=ROOT/'data/research_h124_20261024')
    a=p.parse_args()
    if a.poll_seconds<5 or a.snapshot_seconds<30 or a.confirmations<1 or not 1<=a.chunk<=100 or a.lookback_blocks<1 or a.wallet_limit<0:p.error('Invalid timing/block/cohort limits')
    store=Store(a.state_dir);collector=Collector(store,a.confirmations,a.lookback_blocks,a.chunk,start_block=a.start_block)
    models=LiveModels(store,a.wallet_limit,a.wallet_file,a.historical_results)
    if a.universe_seconds<15 or not 1<=a.universe_batch<=1000:p.error('Invalid universe schedule')
    if a.universe_seed:
        from .universe import UniverseScanner,universe_loop,discovery_loop
        from defi_data.rpc import Rpc
        scan_rpc=Rpc(store.folder/'universe_rpc',batch_size=50,multicall=True,use_cache=False,timeout=15,retry_attempts=1)
        models.universe=UniverseScanner(store,scan_rpc,a.universe_seed,a.universe_batch)
    models.evidence_dir=a.evidence_dir
    models.backtest_dir=a.backtest_dir
    models.research_results=a.research_results;models.research_data=a.research_data
    if a.liquidity_seconds<60:p.error('Liquidity interval must be >=60 seconds')
    if a.once:
        collector.poll();collector.prices()
        if models.universe:models.universe.scan()
        models.update();models.update_exposures();print('One-shot complete; not a continuing real-time service');return
    stop=threading.Event();server=make_server(store,models,'127.0.0.1',a.port,a.poll_seconds,a.snapshot_seconds)
    threading.Thread(target=collector_loop,args=(collector,stop,a.poll_seconds),daemon=True,name='chain-collector').start()
    if models.universe:threading.Thread(target=universe_loop,args=(models.universe,stop,a.universe_seconds),daemon=True,name='borrower-census').start()
    if models.universe:threading.Thread(target=discovery_loop,args=(models.universe,stop),daemon=True,name='borrower-discovery-gap').start()
    from .liquidity import LiveLiquidity,liquidity_loop
    threading.Thread(target=liquidity_loop,args=(LiveLiquidity(store),stop,a.liquidity_seconds),daemon=True,name='dex-quotes').start()
    threading.Thread(target=model_loop,args=(models,stop,a.snapshot_seconds),daemon=True,name='position-model-worker').start()
    threading.Thread(target=exposure_loop,args=(models,stop,a.snapshot_seconds),daemon=True,name='exposure-worker').start()
    print(f'DASHBOARD http://127.0.0.1:{a.port} | events poll {a.poll_seconds:g}s | positions/models {a.snapshot_seconds:g}s | confirmations {a.confirmations}',flush=True)
    try:server.serve_forever(poll_interval=.5)
    except KeyboardInterrupt:pass
    finally:stop.set();server.server_close()

if __name__=='__main__':main()
