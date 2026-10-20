"""Run prior stages against final M3 runtime, preserving historical evidence files."""
import json,os,runpy
from datetime import datetime,timezone
from m1_acceptance import ROOT
E={'run_at':datetime.now(timezone.utc).isoformat(),'runs':[]}
settings={'M2_EVIDENCE':'M3-M2-core-regression.json','M2_LEGACY_EVIDENCE':'M3-M2-legacy-regression.json','M2_PERMISSIONS_EVIDENCE':'M3-M2-permissions-regression.json','M2_BASE_EVIDENCE':'M3-M2-core-regression.json','M2_SECONDARY_LOG':'m3-secondary-out.log','M1_EVIDENCE':'M3-M1-regression.json','M1_LOCK_EVIDENCE':'M3-M1-locking-regression.json','M0_EVIDENCE':'M3-ERP-regression.json'}
previous={k:os.environ.get(k) for k in settings};os.environ.update(settings)
try:
    for script in ['m2_acceptance.py','m2_legacy_inventory.py','m2_permissions.py','m1_acceptance.py','m1_locking.py','m0_smoke.py']:
        runpy.run_path(str(ROOT/'tests'/script),run_name='__main__');E['runs'].append({'script':script,'result':'passed'})
    E['result']='passed'
finally:
    for k,v in previous.items():
        if v is None:os.environ.pop(k,None)
        else:os.environ[k]=v
    (ROOT/'../学习资料/10-验收证据/M3-regression-summary.json').write_text(json.dumps(E,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
