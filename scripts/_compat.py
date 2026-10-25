"""Shared dispatcher for legacy script paths; all logic lives in grouped folders."""
from pathlib import Path
import runpy
import sys

ROOT=Path(__file__).resolve().parents[1]

def dispatch(relative,namespace):
    target=(Path(__file__).resolve().parent/relative).resolve()
    target.relative_to(ROOT/'scripts')
    if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
    name=namespace.get('__name__','__main__')
    values=runpy.run_path(str(target),run_name=name)
    if name!='__main__':namespace.update({k:v for k,v in values.items() if not(k.startswith('__') and k.endswith('__'))})
