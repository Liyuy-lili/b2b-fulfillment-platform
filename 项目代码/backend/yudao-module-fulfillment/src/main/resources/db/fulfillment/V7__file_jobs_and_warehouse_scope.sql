-- M6: V1-V6 immutable. V1 warehouse-grant placeholder becomes enforced here.
ALTER TABLE ful_warehouse_grant ADD CONSTRAINT ck_warehouse_permission CHECK(permission_type IN ('READ','OPERATE'));
CREATE TABLE ful_job_gate (
 tenant_id BIGINT NOT NULL, PRIMARY KEY(tenant_id)
) ENGINE=InnoDB;
INSERT INTO ful_job_gate(tenant_id) VALUES(0);
CREATE TABLE ful_private_file (
 id CHAR(36) COLLATE utf8mb4_bin NOT NULL, tenant_id BIGINT NOT NULL, actor_id BIGINT NOT NULL,
 kind VARCHAR(16) NOT NULL, file_name VARCHAR(128) NOT NULL, storage_key VARCHAR(160) COLLATE utf8mb4_bin NOT NULL,
 sha256 CHAR(64) COLLATE utf8mb4_bin NOT NULL, byte_size BIGINT NOT NULL, created_at DATETIME(6) NOT NULL,
 PRIMARY KEY(id), UNIQUE KEY uk_private_tenant(tenant_id,id), UNIQUE KEY uk_storage_key(storage_key),
 CONSTRAINT ck_private_file CHECK(kind IN ('INPUT','RESULT','ERROR') AND byte_size>=0 AND byte_size<=52428800)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE ful_file_job (
 id BIGINT NOT NULL AUTO_INCREMENT, tenant_id BIGINT NOT NULL, actor_id BIGINT NOT NULL,
 job_type VARCHAR(16) NOT NULL, dataset VARCHAR(16) NOT NULL, status VARCHAR(24) NOT NULL DEFAULT 'PENDING',
 source_system VARCHAR(40) COLLATE utf8mb4_bin NOT NULL DEFAULT '', template_version INT NOT NULL DEFAULT 1,
 input_file_id CHAR(36) COLLATE utf8mb4_bin NULL, result_file_id CHAR(36) COLLATE utf8mb4_bin NULL, error_file_id CHAR(36) COLLATE utf8mb4_bin NULL,
 scope_json TEXT NOT NULL, max_source_id BIGINT NOT NULL DEFAULT 0,
 prepared BIT(1) NOT NULL DEFAULT b'0', parse_cursor INT NOT NULL DEFAULT 0, source_cursor BIGINT NOT NULL DEFAULT 0,
 total_rows INT NOT NULL DEFAULT 0, success_rows INT NOT NULL DEFAULT 0, failed_rows INT NOT NULL DEFAULT 0,
 attempts INT NOT NULL DEFAULT 0, total_attempts INT NOT NULL DEFAULT 0, next_attempt_at DATETIME(6) NOT NULL,
 lease_owner VARCHAR(64) NULL, lease_until DATETIME(6) NULL, lease_version BIGINT NOT NULL DEFAULT 0,
 last_error VARCHAR(256) NULL, created_at DATETIME(6) NOT NULL, started_at DATETIME(6) NULL, completed_at DATETIME(6) NULL,
 PRIMARY KEY(id), UNIQUE KEY uk_file_job_tenant(tenant_id,id),
 KEY ix_job_due(status,next_attempt_at,id), KEY ix_job_lease(status,lease_until,id), KEY ix_job_actor(tenant_id,actor_id,id), KEY ix_job_tenant_state(tenant_id,status,lease_until,id),
 CONSTRAINT fk_job_input FOREIGN KEY(tenant_id,input_file_id) REFERENCES ful_private_file(tenant_id,id),
 CONSTRAINT fk_job_result FOREIGN KEY(tenant_id,result_file_id) REFERENCES ful_private_file(tenant_id,id),
 CONSTRAINT fk_job_error FOREIGN KEY(tenant_id,error_file_id) REFERENCES ful_private_file(tenant_id,id),
 CONSTRAINT ck_job_kind CHECK((job_type='IMPORT' AND dataset='DRAFT' AND input_file_id IS NOT NULL) OR (job_type='EXPORT' AND dataset IN ('STOCK','ORDER','SHIPMENT') AND input_file_id IS NULL)),
 CONSTRAINT ck_job_scope CHECK(JSON_VALID(scope_json) AND template_version=1 AND max_source_id>=0),
 CONSTRAINT ck_job_counts CHECK(parse_cursor>=0 AND source_cursor>=0 AND total_rows>=0 AND success_rows>=0 AND failed_rows>=0 AND success_rows+failed_rows<=total_rows AND attempts>=0 AND total_attempts>=attempts AND lease_version>=0),
 CONSTRAINT ck_job_state CHECK((status IN ('RUNNING','CANCEL_REQUESTED') AND lease_owner IS NOT NULL AND lease_until IS NOT NULL) OR (status IN ('PENDING','RETRY_WAIT','SUCCEEDED','PARTIAL_FAILED','FAILED','CANCELLED') AND lease_owner IS NULL AND lease_until IS NULL))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE ful_file_job_row (
 id BIGINT NOT NULL AUTO_INCREMENT, tenant_id BIGINT NOT NULL, job_id BIGINT NOT NULL, row_no INT NOT NULL,
 raw_json TEXT NOT NULL, status VARCHAR(16) NOT NULL DEFAULT 'PENDING', external_no VARCHAR(128) COLLATE utf8mb4_bin NOT NULL DEFAULT '',
 erp_order_id BIGINT NULL, outcome VARCHAR(24) NULL, error_code VARCHAR(128) NULL, updated_at DATETIME(6) NOT NULL,
 PRIMARY KEY(id), UNIQUE KEY uk_job_row(tenant_id,job_id,row_no), KEY ix_job_row_due(tenant_id,job_id,status,row_no),
 CONSTRAINT fk_job_row FOREIGN KEY(tenant_id,job_id) REFERENCES ful_file_job(tenant_id,id),
 CONSTRAINT ck_job_row CHECK(row_no>0 AND JSON_VALID(raw_json) AND OCTET_LENGTH(raw_json)<=4096 AND status IN ('PENDING','SUCCEEDED','FAILED') AND (status<>'SUCCEEDED' OR erp_order_id IS NOT NULL))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE ful_import_identity (
 id BIGINT NOT NULL AUTO_INCREMENT, tenant_id BIGINT NOT NULL, source_system VARCHAR(40) COLLATE utf8mb4_bin NOT NULL,
 external_no VARCHAR(128) COLLATE utf8mb4_bin NOT NULL, request_hash CHAR(64) COLLATE utf8mb4_bin NOT NULL,
 actor_id BIGINT NOT NULL, erp_order_id BIGINT NULL, job_id BIGINT NOT NULL, row_no INT NOT NULL, created_at DATETIME(6) NOT NULL,
 PRIMARY KEY(id), UNIQUE KEY uk_import_identity(tenant_id,source_system,external_no),
 CONSTRAINT fk_import_job FOREIGN KEY(tenant_id,job_id) REFERENCES ful_file_job(tenant_id,id),
 CONSTRAINT ck_import_external CHECK(CHAR_LENGTH(TRIM(external_no))>0 AND CHAR_LENGTH(TRIM(source_system))>0 AND row_no>0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE ful_operation_audit (
 id BIGINT NOT NULL AUTO_INCREMENT, tenant_id BIGINT NOT NULL, actor_id BIGINT NOT NULL, operation VARCHAR(40) NOT NULL,
 object_type VARCHAR(16) NOT NULL, object_id VARCHAR(64) NOT NULL, request_id VARCHAR(128) NOT NULL,
 reason VARCHAR(256) NOT NULL, before_json TEXT NOT NULL, after_json TEXT NOT NULL, created_at DATETIME(6) NOT NULL,
 PRIMARY KEY(id), KEY ix_audit_object(tenant_id,object_type,object_id,id), KEY ix_audit_actor(tenant_id,actor_id,id),
 CONSTRAINT ck_operation_audit CHECK(JSON_VALID(before_json) AND JSON_VALID(after_json) AND CHAR_LENGTH(TRIM(reason))>0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO system_menu(id,name,permission,type,sort,parent_id,path,icon,component,component_name,creator,updater) VALUES
 (50019,'文件任务','fulfillment:job:query',2,7,597,'fulfillment-jobs','ep:document','erp/fulfillment-jobs/index','ErpFulfillmentJobs','fulfillment','fulfillment'),
 (50020,'导入销售草稿','fulfillment:job:import',3,1,50019,'','','','','fulfillment','fulfillment'),
 (50021,'导出数据','fulfillment:job:export',3,2,50019,'','','','','fulfillment','fulfillment'),
 (50022,'重试文件任务','fulfillment:job:retry',3,3,50019,'','','','','fulfillment','fulfillment'),
 (50023,'取消文件任务','fulfillment:job:cancel',3,4,50019,'','','','','fulfillment','fulfillment'),
 (50024,'仓库作业','fulfillment:warehouse:query',2,8,597,'fulfillment-warehouse','ep:office-building','erp/fulfillment-warehouse/index','ErpFulfillmentWarehouse','fulfillment','fulfillment'),
 (50025,'配置仓库授权','fulfillment:warehouse:grant',3,1,50024,'','','','','fulfillment','fulfillment'),
 (50026,'查询业务审计','fulfillment:audit:query',3,2,50024,'','','','','fulfillment','fulfillment');
