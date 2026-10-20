"""Real HTTP + MySQL M0 acceptance. Each run creates separately labelled demo data.
No mocked auth, no direct writes of business records, no automatic cleanup.
"""
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pymysql
import requests

ROOT = Path(__file__).resolve().parents[1]
BASE = os.getenv('API_BASE', 'http://127.0.0.1:48080') + '/admin-api'
SESSION = requests.Session()
SESSION.headers['tenant-id'] = '1'
EVIDENCE = {'run_at': datetime.now(timezone.utc).isoformat(), 'checks': [], 'ids': {}}


def check(name, condition, detail=None):
    if not condition:
        raise AssertionError(f'{name}: {detail}')
    EVIDENCE['checks'].append({'name': name, 'passed': True, 'detail': detail})


def api(method, path, body=None, params=None, success=True):
    response = SESSION.request(method, BASE + path, json=body, params=params, timeout=30)
    response.raise_for_status()
    data = response.json()
    if success:
        if data.get('code') != 0:
            raise AssertionError(f'{method} {path}: {data}')
        return data.get('data')
    return data


def create(kind, body):
    return api('POST', f'/erp/{kind}/create', body)


def approve(kind, ident, status=20, success=True):
    return api('PUT', f'/erp/{kind}/update-status', params={'id': ident, 'status': status}, success=success)


def main():
    conn = pymysql.connect(host=os.getenv('DB_HOST', '127.0.0.1'), port=int(os.getenv('DB_PORT', '33306')),
                           user=os.getenv('DB_USER', 'fulfillment'), password=os.getenv('DB_PASSWORD', 'fulfillment-dev'),
                           database=os.getenv('DB_NAME', 'fulfillment'), charset='utf8mb4', autocommit=True)
    with conn.cursor() as cur:
        cur.execute('SELECT VERSION()')
        EVIDENCE['mysql_version'] = cur.fetchone()[0]
        for table in json.loads((ROOT/'deploy/erp-entities.json').read_text(encoding='utf8')):
            cur.execute('SELECT COLUMN_NAME,DATA_TYPE,NUMERIC_PRECISION,NUMERIC_SCALE,IS_NULLABLE,COLUMN_DEFAULT,CHARACTER_MAXIMUM_LENGTH FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s', (table['table'],))
            metadata = {r[0]: r[1:] for r in cur.fetchall()}
            actual = set(metadata)
            expected = {f['column'] for f in table['fields']} | {'creator','updater','create_time','update_time','deleted','tenant_id'}
            # M2 is an incremental migration, never a rewrite of the M0 schema manifest.
            if table['table']=='erp_stock' and 'ful_reserved_count' in metadata:
                expected.add('ful_reserved_count')
                check('M2 reserved precision',metadata['ful_reserved_count'][0:3]==('decimal',24,6))
            type_errors = []
            for field in table['fields']:
                column = field['column']
                if column not in metadata:
                    continue
                kind, precision, scale, nullable, default, length = metadata[column]
                declared = field['type'].split()[0].lower()
                if kind != declared.split('(')[0]:
                    type_errors.append(column+': SQL type')
                if declared.startswith('decimal') and (precision, scale) != (24, 6):
                    type_errors.append(column+': precision')
                if declared.startswith('varchar') and length != int(declared.split('(')[1][:-1]):
                    type_errors.append(column+': length')
                if field['type'] == 'BIGINT NULL DEFAULT NULL' and (nullable != 'YES' or default is not None):
                    type_errors.append(column+': optional ID default')
            check('schema.'+table['table'], actual == expected and not type_errors,
                  {'column_diff': sorted(actual ^ expected), 'type_errors': type_errors})
        cur.execute("SELECT COUNT(*) FROM system_menu WHERE permission LIKE 'erp:%%' AND deleted=0")
        check('ERP menu permissions loaded', cur.fetchone()[0] >= 100)
        cur.execute("SELECT COUNT(*) FROM system_dict_type WHERE type LIKE 'erp_%%' AND deleted=0")
        check('ERP dictionaries loaded', cur.fetchone()[0] >= 2)

    anonymous = api('GET', '/erp/product/page', params={'pageNo': 1, 'pageSize': 10}, success=False)
    check('Anonymous ERP request rejected', anonymous.get('code') in (401, 403), anonymous.get('code'))
    login = api('POST', '/system/auth/login', {'username': 'admin', 'password': 'admin123'})
    check('Real password login issues token', bool(login.get('accessToken')))
    SESSION.headers['Authorization'] = 'Bearer ' + login['accessToken']
    permissions = api('GET', '/system/auth/get-permission-info')
    check('Authenticated menu returned', bool(permissions.get('menus')))
    run = 'M0-' + uuid.uuid4().hex[:10]
    now = datetime.now().isoformat(timespec='seconds')
    unit = create('product-unit', {'name': run+'-件', 'status': 0})
    category = create('product-category', {'parentId': 0, 'name': run+'-办公耗材', 'code': run, 'sort': 1, 'status': 0})
    warehouse = create('warehouse', {'name': run+'-西安仓', 'sort': 1, 'status': 0, 'warehousePrice': '0', 'truckagePrice': '0'})
    warehouse2 = create('warehouse', {'name': run+'-上海仓', 'sort': 2, 'status': 0, 'warehousePrice': '0', 'truckagePrice': '0'})
    customer = create('customer', {'name': run+'-企业客户', 'sort': 1, 'status': 0})
    supplier = create('supplier', {'name': run+'-供货商', 'sort': 1, 'status': 0})
    account = create('account', {'name': run+'-结算账户', 'no': run, 'sort': 1, 'status': 0})
    product = create('product', {'name': run+'-A4纸', 'barCode': run, 'categoryId': category, 'unitId': unit,
                                 'status': 0, 'purchasePrice': '10.25', 'salePrice': '12.5', 'weight': '0.1'})
    EVIDENCE['ids'].update(product=product, unit=unit, category=category, warehouse=warehouse, warehouse2=warehouse2,
                           customer=customer, supplier=supplier, account=account)
    line = {'productId': product, 'productUnitId': unit, 'productPrice': '10.25', 'count': '100.123456', 'taxPercent': '0'}

    def balances(expected, records):
        with conn.cursor() as cur:
            cur.execute('SELECT `count` FROM erp_stock WHERE tenant_id=1 AND warehouse_id=%s AND product_id=%s AND deleted=0', (warehouse, product))
            row = cur.fetchone()
            value = row[0] if row else Decimal(0)
            cur.execute('SELECT `count`,total_count,biz_type FROM erp_stock_record WHERE tenant_id=1 AND warehouse_id=%s AND product_id=%s AND deleted=0 ORDER BY id', (warehouse, product))
            ledger = cur.fetchall()
            check('Physical inventory balance', value == Decimal(expected), str(value))
            check('Ledger number', len(ledger) == records, len(ledger))
            running = Decimal(0)
            for delta, after, _ in ledger:
                running += delta
                check('Ledger running balance', running == after, str(after))
            check('Ledger sum matches stock', running == value, str(running))
            return [{'delta': str(d), 'after': str(a), 'biz_type': b} for d, a, b in ledger]

    po = create('purchase-order', {'supplierId': supplier, 'accountId': account, 'orderTime': now, 'discountPercent': '0', 'items': [line]})
    approve('purchase-order', po)
    po_detail = api('GET', '/erp/purchase-order/get', params={'id': po})
    inbound = create('purchase-in', {'orderId': po, 'accountId': account, 'inTime': now, 'discountPercent': '0', 'otherPrice': '0',
                                   'items': [dict(line, orderItemId=po_detail['items'][0]['id'], warehouseId=warehouse)]})
    balances('0', 0)
    approve('purchase-in', inbound)
    balances('100.123456', 1)
    repeated = approve('purchase-in', inbound, success=False)
    check('Repeated approval rejected', repeated['code'] != 0, repeated['code'])
    balances('100.123456', 1)
    sale = create('sale-order', {'customerId': customer, 'saleUserId': 1, 'accountId': account, 'orderTime': now,
                                 'discountPercent': '0', 'items': [dict(line, productPrice='12.5')]})
    approve('sale-order', sale)
    sale_detail = api('GET', '/erp/sale-order/get', params={'id': sale})
    outbound = create('sale-out', {'orderId': sale, 'saleUserId': 1, 'accountId': account, 'outTime': now,
                                  'discountPercent': '0', 'otherPrice': '0', 'items': [dict(line, productPrice='12.5',
                                  count='30.12', orderItemId=sale_detail['items'][0]['id'], warehouseId=warehouse)]})
    balances('100.123456', 1)
    approve('sale-out', outbound)
    balances('70.003456', 2)
    check_id = create('stock-check', {'checkTime': now, 'items': [{'warehouseId': warehouse, 'productId': product,
                            'productPrice': '10.25', 'stockCount': '70.003456', 'actualCount': '69.003456', 'count': '-1'}]})
    approve('stock-check', check_id)
    balances('69.003456', 3)
    approve('stock-check', check_id, 10)
    balances('70.003456', 4)
    approve('stock-check', check_id)
    EVIDENCE['ledger'] = balances('69.003456', 5)
    EVIDENCE['ids'].update(purchase_order=po, purchase_in=inbound, sale_order=sale, sale_out=outbound, stock_check=check_id)

    # A valid sales order can exceed current physical stock; approval must roll back.
    large = create('sale-order', {'customerId': customer, 'orderTime': now, 'discountPercent': '0', 'items': [dict(line, count='200')]})
    approve('sale-order', large)
    large_detail = api('GET', '/erp/sale-order/get', params={'id': large})
    failed_out = create('sale-out', {'orderId': large, 'accountId': account, 'outTime': now, 'discountPercent': '0', 'otherPrice': '0',
                                    'items': [dict(line, count='200', orderItemId=large_detail['items'][0]['id'], warehouseId=warehouse)]})
    failed = approve('sale-out', failed_out, success=False)
    check('Insufficient stock rejected', failed['code'] != 0, failed['code'])
    balances('69.003456', 5)
    detail = api('GET', '/erp/sale-out/get', params={'id': failed_out})
    check('Failed approval status rolls back', detail['status'] == 10, detail['status'])
    EVIDENCE['ids'].update(insufficient_stock_order=large, rejected_sale_out=failed_out)
    # Warm all ERP list endpoints: covers joins / projections beyond create path.
    for kind in ['product','customer','supplier','warehouse','account','purchase-order','purchase-in','purchase-return',
                 'sale-order','sale-out','sale-return','stock','stock-record','stock-in','stock-out','stock-move','stock-check',
                 'finance-payment','finance-receipt']:
        api('GET', '/erp/'+kind+'/page', params={'pageNo': 1, 'pageSize': 10})
        check('Page endpoint '+kind, True)
    conn.close()
    EVIDENCE['status'] = 'passed'


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        EVIDENCE['status'] = 'failed'
        EVIDENCE['error'] = str(error)
        raise
    finally:
        target = ROOT/'../学习资料/10-验收证据'/os.getenv('M0_EVIDENCE','M0-smoke.json')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(EVIDENCE, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
        print(f"M0: {EVIDENCE.get('status')}, {len(EVIDENCE['checks'])} checks. Evidence: {target}")
