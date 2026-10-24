"""Collect historical revision-6 risk parameters for the experimental pair study."""
import argparse,json,csv
from pathlib import Path
from .rpc import Rpc
from .pipeline import registry,call_request
from .evm import words,uint

def main():
    p=argparse.ArgumentParser();p.add_argument('--snapshot',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    scope=json.loads((a.snapshot/'scope.json').read_text(encoding='utf8'));block=scope['block']
    if scope['pool_revision']!=6:raise ValueError('Parameter adapter supports revision 6 only')
    with (a.snapshot/'reserve_metadata.csv').open(encoding='utf-8-sig',newline='') as f:reserves=list(csv.DictReader(f))
    with (a.snapshot/'positions.csv').open(encoding='utf-8-sig',newline='') as f:positions=list(csv.DictReader(f))
    a.out.parent.mkdir(parents=True,exist_ok=True);rpc=Rpc(a.out.parent/'risk_rpc_cache',batch_size=50,multicall=True,timeout=10,retry_attempts=1)
    pool,oracle,provider=registry(rpc,block);tokens=[r['token'] for r in reserves]
    raw=rpc.many([call_request(provider,'getReserveConfigurationData(address)',[t],block) for t in tokens])
    fees=rpc.many([call_request(provider,'getLiquidationProtocolFee(address)',[t],block) for t in tokens])
    bonus={t:max(0,uint(words(v)[3])/10000-1) for t,v in zip(tokens,raw)}
    fee={t:uint(words(v)[0])/10000 for t,v in zip(tokens,fees)}
    mode_bonuses={};bitmaps={};categories={r['token']:int(r['category']) for r in reserves}
    for mode in sorted({int(r['emode']) for r in positions}-{0}):
        w=words(rpc.one(*call_request(pool,'getEModeCategoryData(uint8)',[mode],block)))
        if uint(w[0])!=32:raise ValueError('Unsupported legacy E-mode ABI')
        mode_bonuses[str(mode)]=uint(w[3])/10000-1
        bitmap=rpc.one(*call_request(pool,'getEModeCategoryCollateralBitmap(uint8)',[mode],block))
        bitmaps[str(mode)]=str(uint(words(bitmap)[0]))
    result={'block':block,'hash':rpc.one('eth_getBlockByNumber',[hex(block),False])['hash'],'pool_revision':6,
      'bonus_by_token':bonus,'protocol_fee_by_token':fee,'emode_bonus':mode_bonuses,'reserve_category':categories,
      'emode_collateral_bitmap':bitmaps,'reserve_ids':{r['token']:int(r['reserve_id']) for r in reserves},
      'source':'historical ProtocolDataProvider and Pool eth_call, explicit revision-6 block',
      'note':'Parameters only; not a transaction replay or liquidity calibration'}
    a.out.write_text(json.dumps(result,indent=2),encoding='utf8');print('Collected parameters for',len(tokens),'reserves,',len(mode_bonuses),'E-mode categories')

if __name__=='__main__':main()
