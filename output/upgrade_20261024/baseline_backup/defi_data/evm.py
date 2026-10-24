"""Minimal Ethereum ABI for static values; Keccak-256 (not SHA3-256)."""
import re

MASK = (1 << 64) - 1
RC = [0x1,0x8082,0x800000000000808a,0x8000000080008000,0x808b,0x80000001,
      0x8000000080008081,0x8000000000008009,0x8a,0x88,0x80008009,0x8000000a,
      0x8000808b,0x800000000000008b,0x8000000000008089,0x8000000000008003,
      0x8000000000008002,0x8000000000000080,0x800a,0x800000008000000a,
      0x8000000080008081,0x8000000000008080,0x80000001,0x8000000080008008]
ROT = [[0,36,3,41,18],[1,44,10,45,2],[62,6,43,15,61],[28,55,25,21,56],[27,20,39,8,14]]

def keccak(data: bytes) -> bytes:
    rate = 136
    padded = bytearray(data)
    padded.append(1)
    padded.extend(b'\0' * ((rate - len(padded) % rate) % rate))
    padded[-1] |= 128
    a = [0] * 25
    def rol(v, n): return ((v << n) | (v >> ((64-n) % 64))) & MASK
    for start in range(0, len(padded), rate):
        for i in range(rate//8):
            a[i] ^= int.from_bytes(padded[start+8*i:start+8*i+8], 'little')
        for rc in RC:
            c = [a[x]^a[x+5]^a[x+10]^a[x+15]^a[x+20] for x in range(5)]
            d = [c[(x-1)%5]^rol(c[(x+1)%5],1) for x in range(5)]
            a = [a[x+5*y]^d[x] for y in range(5) for x in range(5)]
            b = [0]*25
            for x in range(5):
                for y in range(5): b[y+5*((2*x+3*y)%5)] = rol(a[x+5*y],ROT[x][y])
            a = [(b[x+5*y]^((~b[(x+1)%5+5*y])&b[(x+2)%5+5*y])) & MASK
                 for y in range(5) for x in range(5)]
            a[0] ^= rc
    return b''.join(v.to_bytes(8,'little') for v in a)[:32]

def topic(signature): return '0x' + keccak(signature.encode()).hex()
def words(result):
    data = result.removeprefix('0x')
    if len(data) % 64: raise ValueError('Malformed ABI output')
    return [data[i:i+64] for i in range(0,len(data),64)]
def addr(word): return '0x'+word[-40:].lower()
def uint(word): return int(word,16)
def encode_arg(value):
    if isinstance(value,int):
        if not -(1<<255)<=value<(1<<256):raise ValueError('Integer outside ABI word')
        return f'{value % (1<<256):064x}'
    return value.removeprefix('0x').zfill(64)
def calldata(signature,*args): return topic(signature)[:10]+''.join(encode_arg(v) for v in args)
def decode_string(result):
    w=words(result)
    if len(w)==1: return bytes.fromhex(w[0]).rstrip(b'\0').decode('utf-8',errors='replace')
    raw=bytes.fromhex(result[2:]); offset=uint(w[0]); length=int.from_bytes(raw[offset:offset+32],'big')
    return raw[offset+32:offset+32+length].decode('utf-8',errors='replace')
def address_array(result):
    w=words(result); start=uint(w[0])//32; length=uint(w[start])
    return [addr(v) for v in w[start+1:start+1+length]]

def parse_events(source):
    result={}
    for name,body in re.findall(r'event\s+(\w+)\s*\((.*?)\)\s*;',source,re.S):
        fields=[]
        for part in body.split(','):
            tokens=part.strip().split()
            if len(tokens)<2: raise ValueError(f'Unsupported event field: {part}')
            typ=tokens[0]
            typ={'Id':'bytes32','uint':'uint256','DataTypes.InterestRateMode':'uint8'}.get(typ,typ)
            if typ not in ('address','bool','bytes32','string','bytes') and not re.fullmatch(r'uint\d+',typ):
                break  # Dynamic/tuple events are outside this decoder's explicit scope.
            fields.append((tokens[-1],typ,'indexed' in tokens))
        else:
            signature=name+'('+','.join(t for _,t,_ in fields)+')'
            result[name]={'signature':signature,'topic':topic(signature),'fields':fields}
    return result

def decode_event(log,spec):
    if any(typ in ('string','bytes') for _,typ,_ in spec['fields']):
        data=bytes.fromhex(log['data'][2:]);head=0;topics=iter(log['topics'][1:]);result={}
        head_length=sum(not indexed for _,_,indexed in spec['fields'])*32
        end=head_length
        for name,typ,indexed in spec['fields']:
            if indexed:word=next(topics).removeprefix('0x')
            else:
                if head+32>len(data):raise ValueError('Truncated ABI head')
                word=data[head:head+32].hex();head+=32
            if typ in ('string','bytes') and not indexed:
                offset=uint(word)
                if offset<head_length or offset%32 or offset+32>len(data):raise ValueError('Invalid dynamic ABI offset')
                length=int.from_bytes(data[offset:offset+32],'big');tail=offset+32+length
                if tail>len(data):raise ValueError('Truncated ABI string')
                result[name]=data[offset+32:tail].decode('utf8') if typ=='string' else '0x'+data[offset+32:tail].hex()
                end=max(end,offset+32+((length+31)//32)*32)
            elif typ in ('string','bytes'):result[name]='0x'+word
            else:result[name]=addr(word) if typ=='address' else ('0x'+word if typ=='bytes32' else uint(word))
        if end!=len(data):raise ValueError('Unexpected extra dynamic ABI bytes')
        return result
    ts=iter(log['topics'][1:]); ds=iter(words(log['data'])); result={}
    for name,typ,indexed in spec['fields']:
        word=next(ts).removeprefix('0x') if indexed else next(ds)
        result[name]=addr(word) if typ=='address' else ('0x'+word if typ=='bytes32' else uint(word))
    try: next(ds); raise ValueError('Unexpected extra ABI words')
    except StopIteration: pass
    return result
