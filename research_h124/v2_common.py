"""Generation-two outputs: old data and model runs remain read-only inputs."""
import json
from .common import CANONICAL,SOURCE,DATA as H1_DATA,OUT as V1_OUT,save,write,read,digest,now,connect,worker_lock
DATA=CANONICAL/'data/research_h124_v2_20261024'
OUT=CANONICAL/'results/research_h124_v2_20261024'

def load(path,default=None):
    import json
    return json.loads(path.read_text(encoding='utf8')) if path.exists() else default

def write_npz(path,**arrays):
    import numpy as np,uuid
    from .common import atomic_replace
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.stem+'.'+uuid.uuid4().hex+'.tmp.npz')
    np.savez_compressed(tmp,**arrays);atomic_replace(tmp,path)
