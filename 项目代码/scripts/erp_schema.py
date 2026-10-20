import os
"""Generate and verify the M0 ERP schema against every enabled ERP DO.

Not the upstream official ERP SQL. Decisions on SQL types/indices are ours.
Run from any directory with Python 3: python scripts/erp_schema.py [--check].
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'backend/yudao-module-erp/src/main/java/cn/iocoder/yudao/module/erp/dal/dataobject'


def snake(name):
    return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()


def model():
    tables = []
    for path in sorted(SOURCE.rglob('*.java')):
        source = path.read_text(encoding='utf-8')
        match = re.search(r'@TableName\(\s*(?:value\s*=\s*)?"([^"]+)"', source)
        if not match:
            raise ValueError(f'Unmapped DO: {path}')
        if '@TableField' in source:
            raise ValueError(f'Review explicit mapping before generating: {path}')
        fields = []
        for java_type, name in re.findall(r'private\s+(\w+)\s+(\w+)\s*;', source):
            column = snake(name)
            if name == 'id':
                sql_type = 'BIGINT NOT NULL AUTO_INCREMENT'
            elif java_type == 'BigDecimal':
                sql_type = 'DECIMAL(24,6) NULL DEFAULT 0'
            elif java_type == 'LocalDateTime':
                sql_type = 'DATETIME NULL'
            elif java_type in ('Long', 'Integer'):
                sql_type = 'BIGINT NULL DEFAULT NULL' if java_type == 'Long' else 'INT NULL DEFAULT 0'
            elif java_type == 'Boolean':
                sql_type = 'BIT(1) NOT NULL DEFAULT b\'0\''
            elif java_type == 'String':
                size = 1024 if name in ('remark', 'fileUrl') else 64 if name in ('no', 'bizNo', 'barCode', 'code') else 255
                sql_type = f'VARCHAR({size}) NULL'
            else:
                raise ValueError(f'Unreviewed type: {java_type}')
            if match[1] == 'erp_stock' and name in ('productId', 'warehouseId'):
                sql_type = 'BIGINT NOT NULL'
            if match[1] == 'erp_stock' and name == 'count':
                sql_type = 'DECIMAL(24,6) NOT NULL DEFAULT 0'
            fields.append({'java': name, 'column': column, 'type': sql_type})
        tables.append({'table': match[1], 'source': os.path.relpath(path,ROOT).replace(chr(92),"/"),
                       'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'fields': fields})
    return tables


def outputs():
    tables = model()
    sql = ['-- Derived from pinned public ERP DOs; see docs/baseline.lock.json.',
           '-- Project-authored schema, not official upstream ERP DDL.',
           '-- Empty database only. No DROP / automatic destructive reset.',
           'SET NAMES utf8mb4;', '']
    audit = ["`creator` VARCHAR(64) NOT NULL DEFAULT ''", '`create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP',
             "`updater` VARCHAR(64) NOT NULL DEFAULT ''", '`update_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP',
             "`deleted` BIT(1) NOT NULL DEFAULT b'0'", '`tenant_id` BIGINT NOT NULL DEFAULT 0']
    manifest = ['# ERP 实体与 DDL 清单', '', '由 `python scripts/erp_schema.py` 生成，SQL 为本项目补齐，不是上游官方 ERP SQL。', '',
                '类型：数量、金额均 DECIMAL(24,6)；时间 DATETIME；MySQL 自增主键。所有表补齐 BaseDO 审计、逻辑删除、tenant_id。', '',
                '可选关联 ID 缺省 NULL（业务以 null 表示未选择）；整数、金额缺省 0。实际必填性沿用接口校验。库存身份和余额强制非空。',
                '库存使用租户+商品+仓库唯一键；单据号和商品条码按租户及逻辑删除标记约束。M2 再加入预占与非负约束。', '',
                '| 表 | 实体 | 业务列 |', '| --- | --- | --- |']
    for table in tables:
        name = table['table']
        columns = [f"`{f['column']}` {f['type']}" for f in table['fields']] + audit + ['PRIMARY KEY (`id`)']
        fields = {f['column'] for f in table['fields']}
        if name == 'erp_stock':
            columns.append('UNIQUE KEY `uk_stock_identity` (`tenant_id`,`product_id`,`warehouse_id`)')
        if 'no' in fields:
            columns.append('UNIQUE KEY `uk_tenant_no` (`tenant_id`,`no`,`deleted`)')
        if 'bar_code' in fields:
            columns.append('UNIQUE KEY `uk_tenant_barcode` (`tenant_id`,`bar_code`,`deleted`)')
        for column in sorted(fields):
            if column.endswith('_id') and column != 'id':
                columns.append(f'KEY `idx_{column}` (`tenant_id`,`{column}`)')
        columns.append('KEY `idx_tenant_created` (`tenant_id`,`create_time`,`id`)')
        sql += [f'-- {table["source"]}', f'CREATE TABLE `{name}` (', '  ' + ',\n  '.join(columns),
                ') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;', '']
        manifest.append(f'| `{name}` | [{Path(table["source"]).name}](../../{table["source"]}) | ' + ', '.join(f"`{f['column']}`" for f in table['fields']) + ' |')
    manifest += ['', f'总计：{len(tables)} 张 ERP 表；每张另含 6 个公共列。', '',
                 '统计 XML 涉及采购入库/退货及销售出库/退货，均包含在清单。初始化后应再与 information_schema 做全量字段比对。', '']
    return {ROOT/'deploy/sql/010-erp.sql': '\n'.join(sql),
            ROOT/'../学习资料/10-验收证据/M0-erp-schema.md': '\n'.join(manifest),
            ROOT/'deploy/erp-entities.json': json.dumps(tables, ensure_ascii=False, indent=2)+'\n'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    for path, content in outputs().items():
        if args.check:
            if not path.exists() or path.read_text(encoding='utf-8') != content:
                raise SystemExit(f'Schema drift: {path}')
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
    print(f'ERP schema: {len(model())} entities covered; {"checked" if args.check else "generated"}.')
