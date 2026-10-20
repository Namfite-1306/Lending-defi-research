"""Explicit ABI for Multicall3 aggregate3; no third-party ABI dependency."""
from .evm import topic
def word(n):return n.to_bytes(32,'big')
def encode_aggregate(calls):
    tuples=[]
    for c in calls:
        data=bytes.fromhex(c['data'][2:]);padded=data+b'\0'*((-len(data))%32)
        tuples.append(bytes.fromhex(c['to'][2:]).rjust(32,b'\0')+word(1)+word(96)+word(len(data))+padded)
    offset=32*len(calls);offsets=[]
    for t in tuples:offsets.append(word(offset));offset+=len(t)
    payload=word(32)+word(len(calls))+b''.join(offsets)+b''.join(tuples)
    return topic('aggregate3((address,bool,bytes)[])')[:10]+payload.hex()
def decode_aggregate(value):
    raw=bytes.fromhex(value[2:])
    def num(o):
        if o<0 or o+32>len(raw):raise ValueError('Truncated Multicall ABI')
        return int.from_bytes(raw[o:o+32],'big')
    start=num(0);n=num(start);content=start+32;result=[]
    if n>10000:raise ValueError('Unreasonable Multicall array size')
    for i in range(n):
        t=content+num(content+32*i);success=num(t);b=t+num(t+32);length=num(b)
        if success not in (0,1) or b+32+length>len(raw):raise ValueError('Invalid Multicall tuple')
        result.append((bool(success),'0x'+raw[b+32:b+32+length].hex()))
    return result
