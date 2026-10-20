-- M4.3 reports only. Executed V1-V4 and business facts remain unchanged.
CREATE INDEX ix_reconcile_tenant_id ON erp_stock(tenant_id,id);
CREATE INDEX ix_reconcile_tenant_id ON erp_stock_record(tenant_id,id);
CREATE INDEX ix_reconcile_tenant_id ON erp_sale_order(tenant_id,id);
CREATE INDEX ix_reconcile_tenant_id ON erp_sale_order_items(tenant_id,id);
CREATE INDEX ix_reconcile_tenant_id ON erp_sale_out(tenant_id,id);
CREATE INDEX ix_reconcile_tenant_id ON erp_sale_out_items(tenant_id,id);
CREATE INDEX ix_reconcile_tenant_id ON erp_sale_return(tenant_id,id);
CREATE INDEX ix_reconcile_tenant_id ON erp_sale_return_items(tenant_id,id);
CREATE INDEX ix_reconcile_tenant_id ON ful_cancellation(tenant_id,id);
CREATE INDEX ix_reconcile_tenant_id ON ful_return(tenant_id,id);
CREATE INDEX ix_reconcile_tenant_id ON ful_return_item(tenant_id,id);
CREATE TABLE ful_reconcile_run (
 id BIGINT NOT NULL AUTO_INCREMENT, tenant_id BIGINT NOT NULL, actor_id BIGINT NOT NULL,
 rule_version VARCHAR(32) COLLATE utf8mb4_bin NOT NULL, scope VARCHAR(16) NOT NULL,
 snapshot_at DATETIME(6) NOT NULL, finished_at DATETIME(6) NOT NULL,
 scanned_count INT NOT NULL, difference_count INT NOT NULL, table_counts_json MEDIUMTEXT NOT NULL,
 PRIMARY KEY(id), UNIQUE KEY uk_reconcile_run(tenant_id,id), KEY ix_reconcile_actor(tenant_id,actor_id,id),
 CONSTRAINT ck_reconcile_run CHECK(scope='TENANT' AND scanned_count>=0 AND difference_count>=0 AND difference_count<=2000)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE ful_reconcile_item (
 id BIGINT NOT NULL AUTO_INCREMENT, tenant_id BIGINT NOT NULL, run_id BIGINT NOT NULL,
 rule_code VARCHAR(64) COLLATE utf8mb4_bin NOT NULL, object_type VARCHAR(64) NOT NULL, object_id BIGINT NOT NULL,
 order_id BIGINT NULL, product_id BIGINT NULL, warehouse_id BIGINT NULL,
 expected_value VARCHAR(512) NOT NULL, actual_value VARCHAR(512) NOT NULL, detail VARCHAR(512) NOT NULL,
 resolution_status VARCHAR(16) COLLATE utf8mb4_bin NOT NULL DEFAULT 'OPEN',
 PRIMARY KEY(id), UNIQUE KEY uk_reconcile_item(tenant_id,run_id,id), KEY ix_reconcile_items(tenant_id,run_id,id),
 CONSTRAINT fk_reconcile_item FOREIGN KEY(tenant_id,run_id) REFERENCES ful_reconcile_run(tenant_id,id),
 CONSTRAINT ck_reconcile_resolution CHECK(resolution_status IN ('OPEN','ACKNOWLEDGED'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE ful_reconcile_review (
 id BIGINT NOT NULL AUTO_INCREMENT, tenant_id BIGINT NOT NULL, run_id BIGINT NOT NULL, item_id BIGINT NOT NULL,
 actor_id BIGINT NOT NULL, note VARCHAR(256) NOT NULL, reviewed_at DATETIME(6) NOT NULL,
 PRIMARY KEY(id), KEY ix_reconcile_reviews(tenant_id,run_id,item_id,id),
 CONSTRAINT fk_reconcile_review FOREIGN KEY(tenant_id,run_id,item_id) REFERENCES ful_reconcile_item(tenant_id,run_id,id),
 CONSTRAINT ck_reconcile_note CHECK(CHAR_LENGTH(TRIM(note))>0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO system_menu(id,name,permission,type,sort,parent_id,path,icon,component,component_name,creator,updater) VALUES
 (50013,'库存与履约核对','fulfillment:reconcile:query',2,6,597,'reconciliation','ep:document-checked','erp/reconciliation/index','ErpReconciliation','fulfillment','fulfillment'),
 (50014,'执行全租户核对','fulfillment:reconcile:run',3,1,50013,'','','','','fulfillment','fulfillment'),
 (50015,'确认核对差异','fulfillment:reconcile:review',3,2,50013,'','','','','fulfillment','fulfillment');
