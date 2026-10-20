"""Activate verified M4.1 jar on the main local demo, audit old overdue holds,
then restart all owned dependencies and verify durable facts. No SQL business writes.
Run only after isolated acceptance and with other writers paused.
"""
import json, os, runpy, shutil, subprocess, time
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from m1_acceptance import ROOT, sql
from m3_acceptance import M3Client

E={'run_at':datetime.now(timezone.utc).isoformat(),'database':'fulfillment','checks':[]}

def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))

def run(script):
    shell=os.getenv('M0_PWSH') or shutil.which('pwsh')
    log=ROOT/'.local'/('m4-main-'+script+'.log')
    with log.open('wb') as out:result=subprocess.run([shell,'-NoProfile','-File',str(ROOT/'scripts'/script)],stdout=out,stderr=subprocess.STDOUT,cwd=ROOT,timeout=180)
    check(script+' exit0',result.returncode==0,str(log))

def snapshot():
    return {
        'stocks':sql('SELECT id,tenant_id,product_id,warehouse_id,`count`,ful_reserved_count FROM erp_stock ORDER BY id'),
        'items':sql('SELECT id,tenant_id,open_qty,reserved_qty,shipped_qty,cancelled_qty,returned_qty FROM ful_order_item ORDER BY id'),
        'physical':sql('SELECT id,tenant_id,product_id,warehouse_id,`count`,total_count FROM erp_stock_record ORDER BY id'),
        'shipments':sql('SELECT id,tenant_id,status,erp_sale_out_id,shipped_at,delivered_at FROM ful_shipment ORDER BY id'),
        'reservations':sql('SELECT id,tenant_id,order_item_id,product_id,warehouse_id,held_qty,consumed_qty,released_qty,expire_at FROM ful_reservation ORDER BY id'),
        'expire_ledger':sql("SELECT id,reservation_id,held_delta,actor_id FROM ful_stock_ledger WHERE event_type='EXPIRE' ORDER BY id")
    }

def ready():
    for _ in range(60):
        try:M3Client().login();return
        except Exception:time.sleep(.5)
    raise AssertionError('main login not ready')

def main():
    acceptance=json.loads((ROOT/'../学习资料/10-验收证据/M4.1-expiry-acceptance.json').read_text(encoding='utf-8'))
    check('isolated acceptance passed before activation',acceptance.get('result')=='passed' and acceptance.get('all_owned_processes_stopped'))
    before=snapshot();E['before']=before
    run('Stop-Local.ps1');run('Start-Local.ps1');ready()
    # Main profile's 5-second/50x4 default scan; wait for enabled tenants' old overdue rows.
    end=time.monotonic()+90
    while time.monotonic()<end:
        pending=sql('SELECT r.id FROM ful_reservation r JOIN system_tenant t ON t.id=r.tenant_id WHERE r.active_flag=1 AND r.expire_at<=UTC_TIMESTAMP(6) AND t.deleted=0 AND t.status=0 AND t.expire_time>NOW()')
        if not pending:break
        time.sleep(.5)
    check('valid tenant old overdue holds drained',not pending,pending)
    after=snapshot();E['after']=after
    check('activation never writes physical balances or ledger',before['physical']==after['physical'] and [x[:5] for x in before['stocks']]==[x[:5] for x in after['stocks']])
    check('activation leaves historical shipments and callbacks intact',before['shipments']==after['shipments'])
    previous={x[0]:x for x in before['reservations']};by_stock=defaultdict(Decimal);by_item=defaultdict(Decimal)
    new_ledger=[x for x in after['expire_ledger'] if x[0] not in {v[0] for v in before['expire_ledger']}]
    E['new_expiry_rows']=len(new_ledger)
    for row in after['reservations']:
        old=previous[row[0]];delta=old[5]-row[5]
        check('reservation transition matches remaining held '+str(row[0]),row[6]==old[6] and row[7]==old[7]+delta and delta>=0)
        by_stock[(row[1],row[3],row[4])]+=delta;by_item[row[2]]+=delta
        if delta:
            facts=[x for x in new_ledger if x[1]==row[0]]
            check('one actor0 expiry ledger per activated hold '+str(row[0]),len(facts)==1 and facts[0][2]==-delta and facts[0][3]==0)
    old_stock={x[0]:x for x in before['stocks']}
    check('all stock R decreases equal released held',all(row[5]==old_stock[row[0]][5]-by_stock[(row[1],row[2],row[3])] for row in after['stocks']))
    old_items={x[0]:x for x in before['items']}
    check('all item R moves to open; shipped cancelled returned unchanged',all(row[2]==old_items[row[0]][2]+by_item[row[0]] and row[3]==old_items[row[0]][3]-by_item[row[0]] and row[4:]==old_items[row[0]][4:] for row in after['items']))
    check('main migration history remains 0 through 3',tuple(x[0] for x in sql('SELECT version FROM ful_flyway_schema_history ORDER BY installed_rank'))==('0','1','2','3'))
    # After the initial housekeeping stabilizes, snapshots across a full dependency restart are exact.
    os.environ['RESTART_EVIDENCE']='M4.1-restart.json'
    runpy.run_path(str(ROOT/'tests/m0_restart.py'),run_name='__main__')
    check('complete MySQL Redis backend frontend restart preserves snapshots',json.loads((ROOT/'../学习资料/10-验收证据/M4.1-restart.json').read_text(encoding='utf-8')).get('status')=='passed')
    ready();stable=snapshot();time.sleep(6)
    check('rescan after full dependency restart creates no duplicate effect',stable==snapshot())
    check('main has no duplicate expiry effect',not sql("SELECT tenant_id,reservation_id FROM ful_stock_ledger WHERE event_type='EXPIRE' GROUP BY tenant_id,reservation_id HAVING COUNT(*)>1"))
    check('main H R reservations and ledgers remain consistent',not sql('SELECT s.id FROM erp_stock s WHERE s.ful_reserved_count<>(SELECT COALESCE(SUM(r.held_qty),0) FROM ful_reservation r WHERE r.tenant_id=s.tenant_id AND r.product_id=s.product_id AND r.warehouse_id=s.warehouse_id) OR s.ful_reserved_count<>(SELECT COALESCE(SUM(l.held_delta),0) FROM ful_stock_ledger l WHERE l.tenant_id=s.tenant_id AND l.product_id=s.product_id AND l.warehouse_id=s.warehouse_id) OR s.`count`<>(SELECT COALESCE(SUM(l.`count`),0) FROM erp_stock_record l WHERE l.tenant_id=s.tenant_id AND l.product_id=s.product_id AND l.warehouse_id=s.warehouse_id)'))
    E['result']='passed'

if __name__=='__main__':
    try:main()
    except Exception as exc:E['result']='failed';E['error']=str(exc);raise
    finally:
        (ROOT/'../学习资料/10-验收证据/M4.1-main-activation.json').write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
        print('M4.1 main activation',E.get('result'),len(E['checks']),'checks',flush=True)
