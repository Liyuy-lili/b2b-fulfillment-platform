-- M5: new events only; no fabricated backfill for pre-M5 business history.
CREATE TABLE ful_outbox_event (
 id BIGINT NOT NULL AUTO_INCREMENT, event_id CHAR(36) COLLATE utf8mb4_bin NOT NULL,
 tenant_id BIGINT NOT NULL, order_id BIGINT NOT NULL, aggregate_version BIGINT NOT NULL,
 event_type VARCHAR(40) COLLATE utf8mb4_bin NOT NULL, payload_version INT NOT NULL,
 command_id BIGINT NOT NULL, body MEDIUMTEXT NOT NULL, body_hash CHAR(64) COLLATE utf8mb4_bin NOT NULL,
 status VARCHAR(16) COLLATE utf8mb4_bin NOT NULL DEFAULT 'NEW', attempts INT NOT NULL DEFAULT 0,
 total_attempts INT NOT NULL DEFAULT 0, next_attempt_at DATETIME(6) NOT NULL,
 lease_owner VARCHAR(64) NULL, lease_until DATETIME(6) NULL, lease_version BIGINT NOT NULL DEFAULT 0,
 last_error VARCHAR(512) NULL, created_at DATETIME(6) NOT NULL, sent_at DATETIME(6) NULL,
 PRIMARY KEY(id), UNIQUE KEY uk_outbox_event(event_id), UNIQUE KEY uk_outbox_tenant_event(tenant_id,event_id),
 UNIQUE KEY uk_outbox_version(tenant_id,order_id,aggregate_version,event_type),
 KEY ix_outbox_due(status,next_attempt_at,id), KEY ix_outbox_lease(status,lease_until,id), KEY ix_outbox_order(tenant_id,order_id,id),
 CONSTRAINT fk_outbox_order FOREIGN KEY(tenant_id,order_id) REFERENCES ful_order(tenant_id,id),
 CONSTRAINT fk_outbox_command FOREIGN KEY(tenant_id,command_id) REFERENCES ful_command_record(tenant_id,id),
 CONSTRAINT ck_outbox_payload CHECK(payload_version=1 AND aggregate_version>=0 AND JSON_VALID(body) AND OCTET_LENGTH(body)<=262144),
 CONSTRAINT ck_outbox_attempt CHECK(attempts>=0 AND total_attempts>=attempts AND lease_version>=0),
 CONSTRAINT ck_outbox_state CHECK((status='IN_FLIGHT' AND lease_owner IS NOT NULL AND lease_until IS NOT NULL) OR (status IN ('NEW','RETRY_WAIT','SENT','DEAD') AND lease_owner IS NULL AND lease_until IS NULL))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE ful_outbox_delivery (
 id BIGINT NOT NULL AUTO_INCREMENT, tenant_id BIGINT NOT NULL, event_id CHAR(36) COLLATE utf8mb4_bin NOT NULL,
 lease_version BIGINT NOT NULL, lease_owner VARCHAR(64) NOT NULL,
 result VARCHAR(16) COLLATE utf8mb4_bin NOT NULL DEFAULT 'STARTED', error VARCHAR(512) NULL,
 started_at DATETIME(6) NOT NULL, finished_at DATETIME(6) NULL,
 PRIMARY KEY(id), UNIQUE KEY uk_delivery_lease(tenant_id,event_id,lease_version), KEY ix_delivery_event(tenant_id,event_id,id),
 CONSTRAINT fk_delivery_event FOREIGN KEY(tenant_id,event_id) REFERENCES ful_outbox_event(tenant_id,event_id),
 CONSTRAINT ck_delivery_result CHECK(result IN ('STARTED','ACKED','FAILED','EXPIRED','LATE'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE ful_inbox_event (
 id BIGINT NOT NULL AUTO_INCREMENT, tenant_id BIGINT NOT NULL, event_id CHAR(36) COLLATE utf8mb4_bin NOT NULL,
 consumer_name VARCHAR(64) COLLATE utf8mb4_bin NOT NULL, status VARCHAR(16) COLLATE utf8mb4_bin NOT NULL DEFAULT 'NEW',
 attempts INT NOT NULL DEFAULT 0, total_attempts INT NOT NULL DEFAULT 0, version BIGINT NOT NULL DEFAULT 0,
 next_attempt_at DATETIME(6) NOT NULL, last_error VARCHAR(512) NULL, processed_at DATETIME(6) NULL,
 applied BIT(1) NOT NULL DEFAULT b'0', duplicate_count INT NOT NULL DEFAULT 0, created_at DATETIME(6) NOT NULL,
 PRIMARY KEY(id), UNIQUE KEY uk_inbox_event(tenant_id,consumer_name,event_id), KEY ix_inbox_due(status,next_attempt_at,id),
 CONSTRAINT fk_inbox_event FOREIGN KEY(tenant_id,event_id) REFERENCES ful_outbox_event(tenant_id,event_id),
 CONSTRAINT ck_inbox_attempt CHECK(attempts>=0 AND total_attempts>=attempts AND version>=0 AND duplicate_count>=0),
 CONSTRAINT ck_inbox_state CHECK(status IN ('NEW','RETRY_WAIT','PROCESSED','DEAD') AND (status<>'PROCESSED' OR processed_at IS NOT NULL))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE ful_order_read_model (
 id BIGINT NOT NULL AUTO_INCREMENT, tenant_id BIGINT NOT NULL, order_id BIGINT NOT NULL, observed_version BIGINT NOT NULL,
 source_event_id CHAR(36) COLLATE utf8mb4_bin NULL, snapshot_json MEDIUMTEXT NOT NULL, updated_at DATETIME(6) NOT NULL,
 PRIMARY KEY(id), UNIQUE KEY uk_read_model_order(tenant_id,order_id),
 CONSTRAINT fk_read_model_order FOREIGN KEY(tenant_id,order_id) REFERENCES ful_order(tenant_id,id),
 CONSTRAINT fk_read_model_event FOREIGN KEY(tenant_id,source_event_id) REFERENCES ful_outbox_event(tenant_id,event_id),
 CONSTRAINT ck_read_model CHECK(observed_version>=0 AND JSON_VALID(snapshot_json) AND OCTET_LENGTH(snapshot_json)<=262144)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE ful_message_action (
 id BIGINT NOT NULL AUTO_INCREMENT, tenant_id BIGINT NOT NULL, order_id BIGINT NOT NULL,
 event_id CHAR(36) COLLATE utf8mb4_bin NULL, command_id BIGINT NOT NULL, actor_id BIGINT NOT NULL,
 action VARCHAR(32) COLLATE utf8mb4_bin NOT NULL, reason VARCHAR(256) NOT NULL, outcome VARCHAR(64) NOT NULL,
 created_at DATETIME(6) NOT NULL,
 PRIMARY KEY(id), UNIQUE KEY uk_message_action(tenant_id,command_id), KEY ix_message_action_order(tenant_id,order_id,id),
 CONSTRAINT fk_message_action_order FOREIGN KEY(tenant_id,order_id) REFERENCES ful_order(tenant_id,id),
 CONSTRAINT fk_message_action_event FOREIGN KEY(tenant_id,event_id) REFERENCES ful_outbox_event(tenant_id,event_id),
 CONSTRAINT fk_message_action_command FOREIGN KEY(tenant_id,command_id) REFERENCES ful_command_record(tenant_id,id),
 CONSTRAINT ck_message_action CHECK(action IN ('REPUBLISH','RETRY_CONSUME','REBUILD') AND CHAR_LENGTH(TRIM(reason))>0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO system_menu(id,name,permission,type,sort,parent_id,path,icon,component,component_name,creator,updater) VALUES
 (50016,'查询可靠消息','fulfillment:message:query',3,16,50000,'','','','','fulfillment','fulfillment'),
 (50017,'重放可靠消息','fulfillment:message:replay',3,17,50000,'','','','','fulfillment','fulfillment'),
 (50018,'重建履约读模型','fulfillment:message:rebuild',3,18,50000,'','','','','fulfillment','fulfillment');
