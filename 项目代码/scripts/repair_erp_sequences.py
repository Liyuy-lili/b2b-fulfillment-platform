"""Explicit local maintenance after lost Redis counters; raises counters only.

Uses existing SQL business numbers (including all tenants and deleted rows).
Never modifies business tables. Pause ERP writes during this maintenance.
Requires tests/requirements.txt. Redis EVAL applies each raise atomically.
"""
import json
import os
import socket
from datetime import datetime
from pathlib import Path

import pymysql

TABLES = {'QTRK':'erp_stock_in', 'QCKD':'erp_stock_out', 'QCDB':'erp_stock_move',
          'QCPD':'erp_stock_check', 'XSDD':'erp_sale_order', 'XSCK':'erp_sale_out',
          'XSTH':'erp_sale_return', 'CGDD':'erp_purchase_order', 'CGRK':'erp_purchase_in',
          'CGTH':'erp_purchase_return', 'FKD':'erp_finance_payment', 'SKD':'erp_finance_receipt'}


def redis(*args):
    def read(stream):
        line = stream.readline()
        if not line:
            raise ConnectionError('Redis connection closed')
        kind, payload = line[:1], line[1:-2]
        if kind == b'-':
            raise RuntimeError(payload.decode())
        if kind == b':':
            return int(payload)
        if kind == b'+':
            return payload.decode()
        if kind == b'$':
            length = int(payload)
            if length == -1:
                return None
            data = stream.read(length)
            stream.read(2)
            return data.decode()
        raise RuntimeError('Unexpected Redis response')
    with socket.create_connection(('127.0.0.1', int(os.getenv('REDIS_PORT', '36379'))), timeout=5) as sock:
        def send(items):
            packet = f'*{len(items)}\r\n'.encode()
            for value in items:
                data = str(value).encode()
                packet += f'${len(data)}\r\n'.encode() + data + b'\r\n'
            sock.sendall(packet)
        with sock.makefile('rb') as stream:
            send(['SELECT', os.getenv('REDIS_DATABASE', '0')]); read(stream)
            send(args)
            return read(stream)


if __name__ == '__main__':
    conn = pymysql.connect(host='127.0.0.1', port=int(os.getenv('DB_PORT', '33306')),
        user=os.getenv('DB_USER', 'fulfillment'), password=os.getenv('DB_PASSWORD', 'fulfillment-dev'),
        database=os.getenv('DB_NAME', 'fulfillment'), charset='utf8mb4')
    today = datetime.now().strftime('%Y%m%d')
    result = []
    with conn.cursor() as cursor:
        for prefix, table in TABLES.items():
            no_prefix = prefix + today
            cursor.execute(f'SELECT COALESCE(MAX(CAST(SUBSTRING(no,%s) AS UNSIGNED)),0) FROM `{table}` WHERE no REGEXP %s',
                           (len(no_prefix)+1, '^'+no_prefix+'[0-9]{6,}$'))
            maximum = int(cursor.fetchone()[0])
            # No reset: keep a higher already allocated Redis counter.
            key = 'erp:seq_no:' + no_prefix
            value = redis('EVAL', "local n=tonumber(redis.call('GET',KEYS[1]) or '0'); local m=tonumber(ARGV[1]); if m>n then redis.call('SET',KEYS[1],m,'EX',86400); return m; end; return n;", 1, key, maximum)
            result.append({'prefix': no_prefix, 'database_max': maximum, 'counter_after': value})
    conn.close()
    out = Path(__file__).resolve().parents[1]/'../学习资料/10-验收证据/M0-sequence-repair.json'
    out.write_text(json.dumps({'performed_at':datetime.now().isoformat(), 'database':os.getenv('DB_NAME','fulfillment'), 'results':result},indent=2)+'\n',encoding='utf8')
    print('ERP number counters reconciled upward from existing SQL numbers; no business records changed.')
