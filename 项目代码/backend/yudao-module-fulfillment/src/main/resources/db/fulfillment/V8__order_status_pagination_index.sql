-- M7 measured tenant/status list path. Existing V1-V7 are immutable.
-- Match equality filters before descending id pagination; MySQL scans this
-- ascending index backward. No changes to business facts or stock semantics.
CREATE INDEX ix_order_tenant_deleted_status_id ON ful_order(tenant_id,deleted,status,id);
