"""Resolve historical paths after the two-folder migration without duplicate files."""
import json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
WORKSPACE=ROOT.parent
PACK=WORKSPACE/'学习资料'
EVIDENCE=PACK/'10-验收证据'
MANIFEST=json.loads((PACK/'整理清单.json').read_text(encoding='utf-8'))
EXACT={e['old']:e['new'] for e in MANIFEST['files']}
EXACT.update(MANIFEST['aliases'])
PREFIXES=sorted(MANIFEST['prefixes'].items(),key=lambda x:len(x[0]),reverse=True)

def legacy(name):
    name=str(name).replace('\\','/')
    if name in EXACT:return WORKSPACE/EXACT[name]
    for old,new in PREFIXES:
        if name==old or name.startswith(old+'/'):return WORKSPACE/new/name[len(old):].lstrip('/')
    return ROOT/name

def portable(path,base=ROOT):return os.path.relpath(path,base).replace('\\','/')
