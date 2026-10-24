import csv,json,hashlib,sqlite3,time,uuid
import os
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
def resolve_source():
    for name in ['merged_7rq_20261023_final','full_7rq_20261022_final']:
        file=ROOT/'results'/name/'manifest.json'
        if file.exists():
            candidate=Path(json.loads(file.read_text(encoding='utf8'))['data_run'])
            if (candidate/'freeze_manifest.json').exists() and (candidate/'history.sqlite').exists():return candidate
    return ROOT/'data/runs/recovery_20261020'
SOURCE=resolve_source()
CANONICAL=SOURCE.parents[2]
DATA=CANONICAL/'data/research_h124_20261024'
OUT=CANONICAL/'results/research_h124_20261024'

def read(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def atomic_replace(tmp,path):
    # Windows can temporarily deny rename while dashboard/AV readers hold an
    # open handle. Retry only this bounded transient operation, never truncate
    # the published file or discard a successfully committed SQLite checkpoint.
    for attempt in range(9):
        try:Path(tmp).replace(path);return
        except PermissionError:
            if attempt==8:raise
            time.sleep(min(.02*2**attempt,.5))
def write(path,rows,fields=None):
    rows=list(rows);path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fields=fields or list(dict.fromkeys(k for row in rows for k in row)) or ['status']
    tmp=path.with_suffix(path.suffix+'.'+uuid.uuid4().hex+'.tmp')
    with tmp.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    atomic_replace(tmp,path)
def save(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.'+uuid.uuid4().hex+'.tmp')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False,default=str),encoding='utf8');atomic_replace(tmp,path)
def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def connect(source=SOURCE):return sqlite3.connect((Path(source)/'history.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
def now():return datetime.now(timezone.utc).isoformat()

@contextmanager
def worker_lock(path):
    """Kernel-held lock, released even on process termination; no stale PID lock."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as f:
        if f.tell()==0:f.write(b'1');f.flush()
        f.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:raise RuntimeError('Another H1 collector already owns this checkpoint directory') from exc
        try:yield
        finally:
            f.seek(0)
            if os.name=='nt':msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f.fileno(),fcntl.LOCK_UN)
