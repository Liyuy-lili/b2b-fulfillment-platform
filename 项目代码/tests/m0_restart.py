"""Stop/start owned local services and assert SQL facts + Redis sequences survive.
Close active ERP edit dialogs and pause writes before running.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import pymysql
import requests

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sequence_tools', ROOT/'scripts/repair_erp_sequences.py')
seq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seq)


def snapshot():
    conn = pymysql.connect(host='127.0.0.1', port=33306, user='fulfillment', password='fulfillment-dev', database='fulfillment')
    tables = json.loads((ROOT/'deploy/erp-entities.json').read_text(encoding='utf8'))
    state = {'row_counts': {}, 'stock': [], 'sequences': {}}
    with conn.cursor() as cur:
        for table in tables:
            cur.execute(f"SELECT COUNT(*) FROM `{table['table']}`")
            state['row_counts'][table['table']] = cur.fetchone()[0]
        cur.execute('SELECT id,tenant_id,product_id,warehouse_id,`count` FROM erp_stock ORDER BY id')
        state['stock'] = [[str(v) for v in row] for row in cur.fetchall()]
        # M1 extension: keep the M0 check backward compatible while proving that
        # migration history, command results and exact snapshots survive restart.
        cur.execute("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME LIKE 'ful\\_%'")
        fulfillment_tables=sorted(r[0] for r in cur.fetchall())
        if fulfillment_tables:
            state['fulfillment_counts']={}
            for table in fulfillment_tables:
                cur.execute('SELECT COUNT(*) FROM `'+table+'`')
                state['fulfillment_counts'][table]=cur.fetchone()[0]
            cur.execute('SELECT tenant_id,actor_id,command_type,idempotency_key,request_hash,response_code,response_json FROM ful_command_record ORDER BY id')
            state['command_results']=[[str(v) for v in row] for row in cur.fetchall()]
            cur.execute('SELECT tenant_id,order_id,erp_order_item_id,ordered_qty,open_qty,reserved_qty,shipped_qty,cancelled_qty,returned_qty FROM ful_order_item ORDER BY id')
            state['quantity_snapshots']=[[str(v) for v in row] for row in cur.fetchall()]
            cur.execute("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='erp_stock' AND COLUMN_NAME='ful_reserved_count'")
            if cur.fetchone()[0]:
                cur.execute('SELECT id,ful_reserved_count FROM erp_stock ORDER BY id')
                state['reserved_stock']=[[str(v) for v in row] for row in cur.fetchall()]
                cur.execute('SELECT id,tenant_id,order_id,order_item_id,product_id,warehouse_id,allocated_qty,held_qty,consumed_qty,released_qty,active_flag,expire_at,version FROM ful_reservation ORDER BY id')
                state['reservation_facts']=[[str(v) for v in row] for row in cur.fetchall()]
                cur.execute('SELECT id,tenant_id,operation_no,line_no,reservation_id,held_delta,reserved_after,event_type,actor_id,reason FROM ful_stock_ledger ORDER BY id')
                state['reservation_ledger']=[[str(v) for v in row] for row in cur.fetchall()]
            if 'ful_cancellation' in fulfillment_tables:
                queries={
                    'shipment_facts':'SELECT id,tenant_id,shipment_no,order_id,warehouse_id,erp_sale_out_id,status,carrier_code,tracking_no,shipped_at,delivered_at FROM ful_shipment ORDER BY id',
                    'shipment_item_facts':'SELECT id,tenant_id,order_id,shipment_id,order_item_id,reservation_id,quantity,erp_sale_out_item_id FROM ful_shipment_item ORDER BY id',
                    'cancellation_facts':'SELECT id,tenant_id,operation_no,order_id,order_item_id,quantity,reason,actor_id FROM ful_cancellation ORDER BY id',
                    'callback_facts':'SELECT id,tenant_id,provider,event_id,shipment_id,payload_hash,result,event_type,occurred_at,received_at,conflict_count,last_conflict_hash FROM ful_callback_event ORDER BY id',
                    'physical_ledger_links':'SELECT id,tenant_id,erp_stock_record_id FROM ful_stock_ledger WHERE erp_stock_record_id IS NOT NULL ORDER BY id'
                }
                for name,query in queries.items():
                    cur.execute(query);state[name]=[[str(v) for v in row] for row in cur.fetchall()]
            if 'ful_return' in fulfillment_tables:
                queries={
                    'return_facts':'SELECT id,tenant_id,return_no,order_id,shipment_id,warehouse_id,status,reason,erp_sale_return_id,received_at,received_by,rejected_at,rejected_by,rejection_reason,creator,updater,create_time,update_time FROM ful_return ORDER BY id',
                    'return_item_facts':'SELECT id,tenant_id,return_id,order_id,shipment_id,order_item_id,shipment_item_id,quantity,erp_sale_return_item_id,erp_stock_record_id FROM ful_return_item ORDER BY id',
                    'return_erp_facts':'SELECT e.id,e.tenant_id,e.order_id,e.status,e.refund_price,e.total_count,e.total_price FROM erp_sale_return e JOIN ful_return r ON r.tenant_id=e.tenant_id AND r.erp_sale_return_id=e.id ORDER BY e.id'
                }
                for name,query in queries.items():
                    cur.execute(query);state[name]=[[str(v) for v in row] for row in cur.fetchall()]

            if 'ful_reconcile_run' in fulfillment_tables:
                for table in ['ful_reconcile_run','ful_reconcile_item','ful_reconcile_review']:
                    cur.execute('SELECT * FROM '+table+' ORDER BY id')
                    state[table+'_facts']=[[str(v) for v in row] for row in cur.fetchall()]
            if 'ful_outbox_event' in fulfillment_tables:
                for table in ['ful_outbox_event','ful_outbox_delivery','ful_inbox_event','ful_order_read_model','ful_message_action']:
                    cur.execute('SELECT * FROM '+table+' ORDER BY id')
                    state[table+'_facts']=[[str(v) for v in row] for row in cur.fetchall()]

            if 'ful_file_job' in fulfillment_tables:
                for table in ['ful_job_gate','ful_private_file','ful_file_job','ful_file_job_row','ful_import_identity','ful_operation_audit','ful_warehouse_grant']:
                    cur.execute('SELECT * FROM '+table+' ORDER BY '+('tenant_id' if table=='ful_job_gate' else 'id'))
                    state[table+'_facts']=[[str(v) for v in row] for row in cur.fetchall()]

    conn.close()
    today = datetime.now().strftime('%Y%m%d')
    for prefix in seq.TABLES:
        key = 'erp:seq_no:' + prefix + today
        state['sequences'][key] = seq.redis('GET', key)
    return state


if __name__ == '__main__':
    shell = os.getenv('M0_PWSH') or shutil.which('pwsh')
    if not shell:
        raise SystemExit('PowerShell 7 required; set M0_PWSH to its executable path.')
    result = {'run_at': datetime.now(timezone.utc).isoformat(), 'before': snapshot()}
    try:
        for name, args in [('Stop-Local.ps1', ['-Dependencies']), ('Start-Local.ps1', [])]:
            # Windows background grandchildren can inherit pipe handles. Files
            # let us wait for PowerShell's exit without waiting for child EOF.
            stdout = ROOT/'.local'/('restart-'+name+'.stdout.log')
            stderr = ROOT/'.local'/('restart-'+name+'.stderr.log')
            with stdout.open('wb') as out, stderr.open('wb') as err:
                completed = subprocess.run([shell, '-NoProfile', '-File', str(ROOT/'scripts'/name)] + args,
                                           cwd=ROOT, stdout=out, stderr=err, timeout=240)
            result[name] = {'exit_code':completed.returncode, 'stdout':stdout.read_text(encoding='utf8',errors='replace'),
                            'stderr':stderr.read_text(encoding='utf8',errors='replace')}
            completed.check_returncode()
        # Listening does not by itself imply all startup hooks have finished.
        for attempt in range(40):
            try:
                response = requests.post('http://127.0.0.1:48080/admin-api/system/auth/login',
                    headers={'tenant-id':'1'}, json={'username':'admin','password':'admin123'}, timeout=3)
                if response.json().get('code') == 0:
                    break
            except requests.RequestException:
                pass
            time.sleep(0.5)
        else:
            raise AssertionError('Real login unavailable after restart')
        result['after'] = snapshot()
        assert result['before'] == result['after'], 'SQL facts or Redis sequence counters changed across restart'
        result['status'] = 'passed'
    except Exception as error:
        result['status'] = 'failed'
        result['error'] = str(error)
        raise
    finally:
        target = ROOT/'../学习资料/10-验收证据'/os.getenv('RESTART_EVIDENCE','M0-restart.json')
        target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        print('M0 full local restart:',result['status'])
