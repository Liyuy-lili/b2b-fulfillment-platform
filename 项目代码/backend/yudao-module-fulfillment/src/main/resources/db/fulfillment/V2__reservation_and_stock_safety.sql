-- M0 initialization and applied V1 remain immutable.
ALTER TABLE erp_stock
  ADD COLUMN ful_reserved_count DECIMAL(24,6) NOT NULL DEFAULT 0 AFTER `count`,
  ADD CONSTRAINT ck_stock_commitment CHECK (`count` >= ful_reserved_count AND ful_reserved_count >= 0),
  ADD CONSTRAINT ck_stock_not_deleted CHECK (deleted = b'0');

ALTER TABLE ful_order ALTER COLUMN allocation_strategy SET DEFAULT 'PRIORITY_SPLIT';
UPDATE ful_order SET allocation_strategy='PRIORITY_SPLIT' WHERE allocation_strategy='PRIORITY';
ALTER TABLE ful_order_item ADD UNIQUE KEY uk_item_order_identity (tenant_id,order_id,id);
ALTER TABLE ful_stock_ledger ADD COLUMN reason VARCHAR(128) NOT NULL DEFAULT '';
ALTER TABLE ful_reservation
  ADD CONSTRAINT fk_reservation_item_order FOREIGN KEY (tenant_id,order_id,order_item_id)
    REFERENCES ful_order_item(tenant_id,order_id,id),
  ADD CONSTRAINT ck_reservation_active CHECK (active_flag=(held_qty>0));

INSERT INTO system_menu (id,name,permission,type,sort,parent_id,path,icon,component,component_name,creator,updater)
VALUES (50002,'分配库存','fulfillment:order:allocate',3,2,50000,'','','','','fulfillment','fulfillment'),
       (50003,'释放预占','fulfillment:order:release',3,3,50000,'','','','','fulfillment','fulfillment'),
       (50004,'查询履约库存','fulfillment:stock:query',3,4,50000,'','','','','fulfillment','fulfillment');
