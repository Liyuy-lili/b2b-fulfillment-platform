-- V1/V2 remain immutable. No shipment/callback rows are produced before M3.
ALTER TABLE ful_shipment ADD UNIQUE KEY uk_shipment_order_identity (tenant_id,order_id,id),
 ADD CONSTRAINT ck_shipment_state CHECK (status IN ('SHIPPED','DELIVERED') AND erp_sale_out_id IS NOT NULL AND shipped_at IS NOT NULL AND (status<>'DELIVERED' OR delivered_at IS NOT NULL));
ALTER TABLE ful_reservation ADD UNIQUE KEY uk_reservation_order_item_identity (tenant_id,order_id,order_item_id,id);
ALTER TABLE ful_shipment_item ADD COLUMN order_id BIGINT NOT NULL,
 ADD UNIQUE KEY uk_shipment_erp_item (tenant_id,erp_sale_out_item_id),
 ADD CONSTRAINT fk_shipment_item_same_order FOREIGN KEY (tenant_id,order_id,shipment_id) REFERENCES ful_shipment(tenant_id,order_id,id),
 ADD CONSTRAINT fk_shipment_item_same_reservation FOREIGN KEY (tenant_id,order_id,order_item_id,reservation_id) REFERENCES ful_reservation(tenant_id,order_id,order_item_id,id),
 ADD CONSTRAINT ck_shipment_erp_item CHECK (erp_sale_out_item_id IS NOT NULL);
ALTER TABLE ful_callback_event ADD COLUMN event_type VARCHAR(32) NOT NULL,
 ADD COLUMN occurred_at DATETIME(6) NOT NULL,
 ADD COLUMN conflict_count INT NOT NULL DEFAULT 0,
 ADD COLUMN last_conflict_hash CHAR(64) NULL;
CREATE TABLE ful_cancellation (
 id BIGINT NOT NULL AUTO_INCREMENT, operation_no VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
 order_id BIGINT NOT NULL, order_item_id BIGINT NOT NULL,
 quantity DECIMAL(24,6) NOT NULL, reason VARCHAR(128) NOT NULL, actor_id BIGINT NOT NULL,
 tenant_id BIGINT NOT NULL, creator VARCHAR(64) NOT NULL DEFAULT '', create_time DATETIME(6) NOT NULL,
 updater VARCHAR(64) NOT NULL DEFAULT '', update_time DATETIME(6) NOT NULL, deleted BIT(1) NOT NULL DEFAULT b'0',
 PRIMARY KEY(id), UNIQUE KEY uk_cancel_operation (tenant_id,operation_no,order_item_id),
 KEY ix_cancellation_order(tenant_id,order_id,id),
 CONSTRAINT fk_cancellation_order_item FOREIGN KEY (tenant_id,order_id,order_item_id) REFERENCES ful_order_item(tenant_id,order_id,id),
 CONSTRAINT ck_cancellation_qty CHECK (quantity>0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO system_menu (id,name,permission,type,sort,parent_id,path,icon,component,component_name,creator,updater) VALUES
 (50005,'取消未发货量','fulfillment:order:cancel',3,5,50000,'','','','','fulfillment','fulfillment'),
 (50006,'确认履约发货','fulfillment:shipment:confirm',3,6,50000,'','','','','fulfillment','fulfillment'),
 (50007,'查询发货记录','fulfillment:shipment:query',3,7,50000,'','','','','fulfillment','fulfillment'),
 (50008,'模拟物流通知','fulfillment:shipment:simulate',3,8,50000,'','','','','fulfillment','fulfillment');
