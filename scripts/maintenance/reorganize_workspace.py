"""One-time, manifest-driven source reorganization. Never touches data/results."""
from pathlib import Path
import json,shutil,os,re

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/restructure_20261026'
moves=json.loads((OUT/'moves.json').read_text(encoding='utf8'))
moves['README.md']='archive/member_rq7/README.md'
for old,new in moves.items():
    src=(ROOT/old).resolve();dest=(ROOT/new).resolve()
    src.relative_to(ROOT);dest.relative_to(ROOT)
    if not src.is_file():raise FileNotFoundError(src)
    if dest.exists():raise FileExistsError(dest)
for old,new in moves.items():
    src=ROOT/old;dest=ROOT/new;backup=OUT/'before'/old
    backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,backup)
    dest.parent.mkdir(parents=True,exist_ok=True);src.rename(dest)
    if old.startswith('scripts/'):
        s=dest.read_text(encoding='utf8').replace('Path(__file__).resolve().parents[2]','Path(__file__).resolve().parents[2]')
        dest.write_text(s,encoding='utf8')
        relative=Path(new).relative_to('scripts').as_posix()
        (ROOT/old).write_text('"""Compatibility entry point; implementation: '+new+'."""\n'
          'if __package__:\n    from ._compat import dispatch\nelse:\n    from _compat import dispatch\n'
          'dispatch('+repr(relative)+', globals())\n',encoding='utf8')
    if old.endswith('.md'):
        s=dest.read_text(encoding='utf8')
        def link(match):
            label,url=match.groups()
            if '://' in url or url.startswith(('#','/')):return match[0]
            target=Path(url.split('#')[0])
            if not target.as_posix() in moves and not (ROOT/target).exists():return match[0]
            resolved=ROOT/moves.get(target.as_posix(),target.as_posix())
            changed=os.path.relpath(resolved,dest.parent).replace(os.sep,'/')
            if '#' in url:changed+='#'+url.split('#',1)[1]
            return '['+label+']('+changed+')'
        s=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',link,s)
        dest.write_text(s,encoding='utf8')
(OUT/'moves.json').write_text(json.dumps(moves,indent=2),encoding='utf8')
print('Moved',len(moves),'files; preserved script compatibility entry points')
