"""Freeze approved historical API payloads for static hosting; never export live data.

Run with the research environment: python scripts/deployment/export_snapshot.py
Requires the local dashboard at http://127.0.0.1:8790 for the 7-RQ/validation views.
"""
import argparse
import gzip
import hashlib
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from defi_live.research import research_data,cascade_result


def scrub(value):
    if isinstance(value,dict):
        return {k:('[redacted]' if k.lower() in {'api_key','apikey','authorization','password','secret','access_token'} else scrub(v)) for k,v in value.items()}
    if isinstance(value,list):return [scrub(v) for v in value]
    if isinstance(value,str):
        if re.search(r'https?://[^\s]*(?:alchemy|infura|quicknode)',value,re.I):return '[RPC endpoint redacted]'
        if re.match(r'^[A-Za-z]:[\\/]',value):
            normalized=value.replace('\\','/')
            parts=normalized.split('/defi-research/',1)
            return parts[1] if len(parts)==2 else '[local path]/'+normalized.rsplit('/',1)[-1]
    return value


def export(base,out):
    if not re.fullmatch(r'http://(?:127\.0\.0\.1|localhost):\d+',base):raise ValueError('Export only from a local dashboard URL')
    def read(route):
        with urllib.request.urlopen(base+'/api/'+route,timeout=60) as response:return json.load(response)
    results=ROOT/'results/research_h124_20261024';data=ROOT/'data/research_h124_20261024'
    research=research_data(results,data)
    scope=research.get('source_stage',{}).get('manifest',{}).get('primary_scope',{})
    if scope.get('required_snapshots')!=13 or scope.get('full_snapshots')!=13:raise ValueError('Approved 13-quarter scope is incomplete')
    lab=read('lab/data');validation=read('validation')
    if set(lab.get('rq',{}))!={str(n) for n in range(1,8)}:raise ValueError('Missing historical RQs')
    stamp=datetime.now(timezone.utc).isoformat()
    metadata={'mode':'frozen_historical','exported_utc':stamp,'live_data_included':False}
    payloads={'research':research,'lab':lab,'validation':validation}
    cascades={}
    for item in research.get('v2',{}).get('event_plan',[]):
        for shock in [.1,.2,.3]:
            for feedback in [True,False]:
                key=f"{item['quarter']}|{shock}|{str(feedback).lower()}"
                cascades[key]=cascade_result(results,data,item['quarter'],shock,feedback)
    manifest={**metadata,'files':{},'primary_end_exclusive':scope.get('primary_end_exclusive'),'full_snapshots':13}
    out.mkdir(parents=True,exist_ok=True)
    for name,value in {**payloads,'cascade':cascades}.items():
        if name!='cascade':value={**value,'deployment':metadata}
        raw=json.dumps(scrub(value),ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf8')
        compressed=gzip.compress(raw,mtime=0);filename=name+'.json.gz'
        (out/filename).write_bytes(compressed)
        manifest['files'][filename]={'sha256':hashlib.sha256(compressed).hexdigest(),'compressed_bytes':len(compressed),'json_bytes':len(raw)}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(manifest,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--base',default='http://127.0.0.1:8790')
    parser.add_argument('--out',type=Path,default=ROOT/'deployment/snapshot')
    args=parser.parse_args();export(args.base,args.out)
