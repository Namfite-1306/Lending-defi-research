import csv,hashlib,json
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'results/research_h123_sources_20261024'
OUT=ROOT/'results/limitations_upgrade_20261026'
PRIMARY_END='2026-04-01T00:00:00+00:00'

def now():return datetime.now(timezone.utc).isoformat()
def read(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8');temp.replace(path)
def write(path,rows):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);rows=list(rows)
    fields=list(dict.fromkeys(k for row in rows for k in row)) or ['status']
    tmp=path.with_suffix(path.suffix+'.tmp')
    with tmp.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    tmp.replace(path)
def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()
