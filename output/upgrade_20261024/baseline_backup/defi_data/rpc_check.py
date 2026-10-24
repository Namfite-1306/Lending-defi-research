"""Read-only RPC diagnostic. Does not create crawl checkpoints or touch audited runs."""
import argparse,json
from pathlib import Path
from .rpc import Rpc,RpcError
from .pipeline import ROOT,CONTRACTS
from .evm import parse_events

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--start-block',type=int,default=21762265);p.add_argument('--end-block',type=int,default=21762300)
    p.add_argument('--require-state',action='store_true')
    p.add_argument('--report',type=Path,default=ROOT/'output/rpc_check/rpc_preflight.json')
    p.add_argument('--test-logs',action='store_true',help='Bounded <=100-block log query after probes; never full crawl')
    a=p.parse_args()
    if a.start_block<0 or a.end_block<a.start_block:p.error('Invalid block range')
    if a.test_logs and a.end_block-a.start_block>=100:p.error('--test-logs limit is 100 blocks')
    rpc=Rpc(ROOT/'data/rpc_cache')
    try:
        report=rpc.preflight(a.start_block,a.end_block,a.report,a.require_state)
        if a.test_logs:
            spec=parse_events((ROOT/'data/sources/IPool.sol').read_text(encoding='utf8'))
            logs=rpc.logs(CONTRACTS['aave_v3'][0],[spec[n]['topic'] for n in CONTRACTS['aave_v3'][2]],a.start_block,a.end_block)
            report['bounded_log_test']={'records':len(logs),'start':a.start_block,'end':a.end_block,'creates_coverage':False}
            a.report.write_text(json.dumps(report,indent=2),encoding='utf8')
        print(json.dumps(report,indent=2));return 0
    except RpcError as e:
        print(f'RPC CHECK FAILED [{e.kind}]: {e}');return 2

if __name__=='__main__':raise SystemExit(main())
