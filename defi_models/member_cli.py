"""Route member modules through the same audited production runner."""
import argparse
import sys
from pathlib import Path


def run_member(models, argv=None):
    from .core import DEFAULT_RUN, ROOT
    from .__main__ import main
    parser=argparse.ArgumentParser(description='Run '+', '.join(f'RQ{i}' for i in models)+' with the shared audited engine.')
    parser.add_argument('--data-run',type=Path,default=DEFAULT_RUN)
    parser.add_argument('--config',type=Path,default=ROOT/'configs/models.full_7rq_20261022.json')
    parser.add_argument('--out',type=Path)
    parser.add_argument('--allow-exploratory',action='store_true')
    if len(models)>1:parser.add_argument('--only',type=int,choices=models)
    args=parser.parse_args(argv)
    selected=[args.only] if getattr(args,'only',None) else models
    command=['all','--models',*[str(i) for i in selected],'--data-run',str(args.data_run),'--config',str(args.config)]
    if args.out:command+=['--out',str(args.out)]
    if args.allow_exploratory:command+=['--allow-exploratory']
    try:return main(command)
    except (ValueError,FileNotFoundError) as exc:
        print(f'ERROR: {exc}',file=sys.stderr)
        return 2
