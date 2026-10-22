"""Conservative proof of WETH→native ETH→minted collateral→Aave loop branches."""
import json,time
from .recovery import RUN,OUT,ROOT,http
from .expansion import read_csv
from .pipeline import CONTRACTS,save_json,csv_write,call
from .rpc import Rpc
from .evm import words,addr,uint,topic,parse_events,decode_event
WETH='0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'

def flatten(node):
    if node.get('error'):return
    yield node
    for child in node.get('calls',[]):yield from flatten(child)


def funded_unwrap(nodes,start,end,account,quantity,native_before):
    """Require an explicit WETH withdrawal and its sole native inflow before mint."""
    for i in range(start+1,end):
        node=nodes[i]
        if (node.get('type')!='CALL' or node.get('from')!=account or node.get('to')!=WETH
            or node.get('input','')[:10]!='0x2e1a7d4d' or native_before[i]!=0):continue
        args=words('0x'+node['input'][10:])
        if len(args)!=1 or uint(args[0])!=quantity:continue
        incoming=[n for n in flatten(node) if n.get('type')=='CALL' and n.get('from')==WETH
                  and n.get('to')==account and int(n.get('value','0x0'),16)==quantity]
        if len(incoming)!=1:continue
        movements=[n for n in nodes[start+1:end] if n.get('type') in ('CALL','CREATE','CREATE2')
                   and int(n.get('value','0x0'),16)>0 and account in (n.get('from'),n.get('to'))]
        if len(movements)==1 and movements[0] is incoming[0]:return i
    return None

def traced(tx,tracer):
    path=RUN/'traces'/f'{tx}_{tracer}.json'
    if path.exists():return json.loads(path.read_text(encoding='utf8'))
    for attempt in range(4):
        try:
            result=http('https://eth.drpc.org','debug_traceTransaction',[tx,{'tracer':tracer}]);save_json(path,result);return result
        except Exception:
            if attempt==3:raise
            time.sleep(2**attempt)

def main():
    records=read_csv(OUT/'recursive_receipt_verification.csv');evidence=[];rpc=Rpc(ROOT/'data/rpc_cache');pool=CONTRACTS['aave_v3'][0]
    transfer=topic('Transfer(address,address,uint256)')
    specs=parse_events((ROOT/'data/sources/IPool.sol').read_text(encoding='utf8'))
    for record in records:
        tx=record['tx'];a=record['account'];b=int(record['block'])
        # Old trace labels must be re-proved by this stricter algorithm. A failed
        # rerun cannot retain a positive label after its evidence is replaced.
        if record.get('status','').startswith('verified') and record['status']!='verified_trace_funded_partial_collateral':continue
        record['status']='unresolved';record['trace_required_for_unresolved']=True
        for key in ('funded_collateral_raw','supplied_collateral_raw','funding_scope','funding_proof_version'):
            record.pop(key,None)
        try:
            trace=traced(tx,'callTracer');pre=traced(tx,'prestateTracer');nodes=list(flatten(trace))
            native_initial=pre.get(a,{}).get('balance')
            if native_initial is None:raise ValueError('No native prestate balance')
            native=int(native_initial,16) if isinstance(native_initial,str) else native_initial
            if native!=0:raise ValueError('Nonzero opening native balance; borrowed funding is not uniquely attributable')
            receipt=rpc.one('eth_getTransactionReceipt',[tx]);txidx=int(receipt['transactionIndex'],16)
            protocol_events=[]
            for log in receipt['logs']:
                if log['address'].lower()!=pool:continue
                for name in ('Borrow','Repay','Supply','Withdraw'):
                    if log['topics'][0]==specs[name]['topic']:
                        decoded=decode_event(log,specs[name])
                        if decoded.get('onBehalfOf',decoded.get('user'))==a:protocol_events.append((name,decoded))
            net_debt=sum(d['amount'] for name,d in protocol_events if name=='Borrow' and d['reserve']==WETH)-sum(d['amount'] for name,d in protocol_events if name=='Repay' and d['reserve']==WETH)
            if net_debt<=0:raise ValueError('No positive net WETH debt added')
            before=uint(call(rpc,WETH,'balanceOf(address)',[a],b-1)[0])
            earlier=rpc.logs(WETH,[transfer],b,b)
            for l in earlier:
                if int(l['transactionIndex'],16)>=txidx or len(l['topics'])!=3:continue
                amount=uint(words(l['data'])[0])
                if addr(l['topics'][1])==a:before-=amount
                if addr(l['topics'][2])==a:before+=amount
            if before!=0:raise ValueError('Nonzero WETH opening balance; attribution left unresolved')
            native_before={}
            for i,n in enumerate(nodes):
                native_before[i]=native
                if n.get('type') not in ('CALL','CREATE','CREATE2'):continue
                value=int(n.get('value','0x0'),16)
                if n.get('from')==a:native-=value
                if n.get('to')==a:native+=value
            proved=False
            for i,n in enumerate(nodes):
                if n.get('type')!='CALL' or n.get('to')!=pool or n.get('from')!=a or n.get('input','')[:10]!='0xa415bcad':continue
                args=words('0x'+n['input'][10:]);loan=addr(args[0]);quantity=uint(args[1])
                if loan!=WETH or addr(args[4])!=a:continue
                for j,s in enumerate(nodes[i+1:],i+1):
                    if s.get('type')!='CALL' or s.get('to')!=pool or s.get('from')!=a or s.get('input','')[:10] not in ('0x617ba037','0xe8eda9df'):continue
                    sw=words('0x'+s['input'][10:]);collateral=addr(sw[0]);supplied=uint(sw[1])
                    if addr(sw[2])!=a or collateral==WETH:continue
                    net_collateral=sum(d['amount'] for name,d in protocol_events if name=='Supply' and d['reserve']==collateral)-sum(d['amount'] for name,d in protocol_events if name=='Withdraw' and d['reserve']==collateral)
                    if net_collateral<=0:continue
                    reborrow=[]
                    for r in nodes[j+1:]:
                        if r.get('type')=='CALL' and r.get('to')==pool and r.get('from')==a and r.get('input','')[:10]=='0xa415bcad':
                            rw=words('0x'+r['input'][10:])
                            if addr(rw[0])==WETH and addr(rw[4])==a:reborrow.append(r)
                    if not reborrow:continue
                    for k,deposit in enumerate(nodes[i+1:j],i+1):
                        if deposit.get('type')!='CALL' or deposit.get('from')!=a or int(deposit.get('value','0x0'),16)!=quantity:continue
                        if native_before[k]!=quantity:continue
                        unwrap_index=funded_unwrap(nodes,i,k,a,quantity,native_before)
                        if unwrap_index is None:continue
                        # Unique borrowed-token incoming transfer before this supply;
                        # supplies in trace and receipt are matched by asset/amount.
                        supply_index=None
                        for log in receipt['logs']:
                            if log['address'].lower()!=pool or not log['topics'] or log['topics'][0]!=specs['Supply']['topic']:continue
                            decoded=decode_event(log,specs['Supply'])
                            if (decoded['reserve']==collateral and decoded['user']==a
                                and decoded['onBehalfOf']==a and decoded['amount']==supplied):
                                supply_index=int(log['logIndex'],16);break
                        if supply_index is None:continue
                        incoming=0
                        for l in receipt['logs']:
                            if l['address'].lower()==WETH and l['topics'] and l['topics'][0]==transfer and len(l['topics'])==3 and int(l['logIndex'],16)<supply_index and addr(l['topics'][2])==a:
                                incoming+=uint(words(l['data'])[0])
                        if incoming!=quantity:continue
                        mints=[]
                        for child in flatten(deposit):
                            if child.get('type')=='CALL' and child.get('to')==collateral and child.get('input','')[:10]=='0x40c10f19':
                                mw=words('0x'+child['input'][10:])
                                if addr(mw[0])==a:mints.append(uint(mw[1]))
                        minted=sum(mints)
                        if not 0<minted<=supplied:continue
                        # Require receipt evidence for the mint as well as its call.
                        receipt_mint=sum(uint(words(l['data'])[0]) for l in receipt['logs'] if l['address'].lower()==collateral and l['topics'] and l['topics'][0]==transfer and len(l['topics'])==3
                            and addr(l['topics'][1])=='0x'+'0'*40 and addr(l['topics'][2])==a and int(l['logIndex'],16)<supply_index)
                        if receipt_mint<minted:continue
                        record['status']='verified_trace_funded_partial_collateral'
                        record['reason']='WETH opening balance zero; borrowed WETH unwrapped; sole native balance funds mint; minted collateral supplied before same-token reborrow'
                        record['trace_required_for_unresolved']=False
                        record['funding_proof_version']=2
                        record['funded_collateral_raw']=str(minted);record['supplied_collateral_raw']=str(supplied)
                        record['funding_scope']='proven minted component only; flash-loan/external remainder not attributed'
                        evidence.append({'tx':tx,'account':a,'borrowed_weth_raw':str(quantity),'native_initial':str(native_initial),
                                         'native_before_conversion':str(native_before[k]),'conversion_contract':deposit['to'],'minted_collateral_raw':str(minted),
                                         'collateral':collateral,'supplied_collateral_raw':str(supplied),'net_weth_debt_added_raw':str(net_debt),
                                         'net_collateral_added_raw':str(net_collateral),'borrow_call_index':i,'unwrap_call_index':unwrap_index,
                                         'supply_call_index':j,'funding_proof_version':2})
                        proved=True;break
                    if proved:break
                if proved:break
            if not proved:record['reason']='Trace acquired; strict WETH/native/mint funding proof not met; remains unresolved'
        except Exception as e:record['reason']='Trace funding check unresolved: '+str(e)[:250]
        print(record['tx'][:12],record['status'],flush=True)
    save_json(RUN/'trace_funding_evidence.json',evidence)
    csv_write(OUT/'recursive_receipt_verification.csv',records)
if __name__=='__main__':main()
