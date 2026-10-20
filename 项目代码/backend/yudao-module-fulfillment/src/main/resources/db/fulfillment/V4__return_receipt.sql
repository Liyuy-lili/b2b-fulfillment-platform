-- Project M4.2: immutable return application and receipt facts. V1-V3 stay unchanged.
ALTER TABLE ful_shipment ADD UNIQUE KEY uk_shipment_origin (tenant_id,order_id,id,warehouse_id);
ALTER TABLE ful_shipment_item ADD UNIQUE KEY uk_shipment_item_return_identity (tenant_id,order_id,shipment_id,order_item_id,id);
CREATE TABLE ful_return (
 id BIGINT NOT NULL AUTO_INCREMENT, return_no VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
 order_id BIGINT NOT NULL, shipment_id BIGINT NOT NULL, warehouse_id BIGINT NOT NULL,
 status VARCHAR(16) COLLATE utf8mb4_bin NOT NULL, reason VARCHAR(128) NOT NULL,
 erp_sale_return_id BIGINT NULL, received_at DATETIME(6) NULL, received_by BIGINT NULL,
 rejected_at DATETIME(6) NULL, rejected_by BIGINT NULL, rejection_reason VARCHAR(128) NULL,
 tenant_id BIGINT NOT NULL, creator VARCHAR(64) NOT NULL DEFAULT '', create_time DATETIME(6) NOT NULL,
 updater VARCHAR(64) NOT NULL DEFAULT '', update_time DATETIME(6) NOT NULL, deleted BIT(1) NOT NULL DEFAULT b'0',
 PRIMARY KEY(id), UNIQUE KEY uk_return_identity(tenant_id,order_id,shipment_id,id),
 UNIQUE KEY uk_return_no(tenant_id,return_no), UNIQUE KEY uk_return_erp(tenant_id,erp_sale_return_id),
 KEY ix_return_order(tenant_id,order_id,id), KEY ix_return_shipment(tenant_id,shipment_id,status,id),
 CONSTRAINT fk_return_origin FOREIGN KEY(tenant_id,order_id,shipment_id,warehouse_id) REFERENCES ful_shipment(tenant_id,order_id,id,warehouse_id),
 CONSTRAINT ck_return_state CHECK(deleted=0 AND (
  (status='REQUESTED' AND erp_sale_return_id IS NULL AND received_at IS NULL AND received_by IS NULL AND rejected_at IS NULL AND rejected_by IS NULL AND rejection_reason IS NULL) OR
  (status='RECEIVED' AND erp_sale_return_id IS NOT NULL AND received_at IS NOT NULL AND received_by IS NOT NULL AND rejected_at IS NULL AND rejected_by IS NULL AND rejection_reason IS NULL) OR
  (status='REJECTED' AND erp_sale_return_id IS NULL AND received_at IS NULL AND received_by IS NULL AND rejected_at IS NOT NULL AND rejected_by IS NOT NULL AND rejection_reason IS NOT NULL AND CHAR_LENGTH(TRIM(rejection_reason))>0)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE ful_return_item (
 id BIGINT NOT NULL AUTO_INCREMENT, return_id BIGINT NOT NULL, order_id BIGINT NOT NULL,
 shipment_id BIGINT NOT NULL, order_item_id BIGINT NOT NULL, shipment_item_id BIGINT NOT NULL,
 quantity DECIMAL(24,6) NOT NULL, erp_sale_return_item_id BIGINT NULL, erp_stock_record_id BIGINT NULL,
 tenant_id BIGINT NOT NULL, creator VARCHAR(64) NOT NULL DEFAULT '', create_time DATETIME(6) NOT NULL,
 updater VARCHAR(64) NOT NULL DEFAULT '', update_time DATETIME(6) NOT NULL, deleted BIT(1) NOT NULL DEFAULT b'0',
 PRIMARY KEY(id), UNIQUE KEY uk_return_item(tenant_id,return_id,shipment_item_id),
 UNIQUE KEY uk_return_erp_item(tenant_id,erp_sale_return_item_id), UNIQUE KEY uk_return_stock_record(tenant_id,erp_stock_record_id),
 KEY ix_return_item_shipment(tenant_id,shipment_item_id,return_id),
 CONSTRAINT fk_return_item_head FOREIGN KEY(tenant_id,order_id,shipment_id,return_id) REFERENCES ful_return(tenant_id,order_id,shipment_id,id),
 CONSTRAINT fk_return_item_origin FOREIGN KEY(tenant_id,order_id,shipment_id,order_item_id,shipment_item_id) REFERENCES ful_shipment_item(tenant_id,order_id,shipment_id,order_item_id,id),
 CONSTRAINT ck_return_item_qty CHECK(quantity>0 AND deleted=0 AND ((erp_sale_return_item_id IS NULL AND erp_stock_record_id IS NULL) OR (erp_sale_return_item_id IS NOT NULL AND erp_stock_record_id IS NOT NULL)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
INSERT INTO system_menu(id,name,permission,type,sort,parent_id,path,icon,component,component_name,creator,updater) VALUES
 (50009,'查询履约退货','fulfillment:return:query',3,9,50000,'','','','','fulfillment','fulfillment'),
 (50010,'申请履约退货','fulfillment:return:create',3,10,50000,'','','','','fulfillment','fulfillment'),
 (50011,'确认退货收货','fulfillment:return:receive',3,11,50000,'','','','','fulfillment','fulfillment'),
 (50012,'拒绝退货申请','fulfillment:return:reject',3,12,50000,'','','','','fulfillment','fulfillment');
