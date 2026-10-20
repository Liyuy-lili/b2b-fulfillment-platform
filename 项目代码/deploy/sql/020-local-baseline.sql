-- Local project setup after generic + ERP DDL, executed only on an empty DB.
-- Preserve system/infra/ERP menu branches, hide other modules and external links.
UPDATE system_menu SET visible = b'0', status = 1
WHERE parent_id = 0 AND id NOT IN (1, 2, 597);

-- Use local database file storage; never call the upstream sample S3 account.
UPDATE infra_file_config SET master = b'0';
UPDATE infra_file_config SET master = b'1' WHERE id = 4;

-- Disable bundled sample integrations. This is project-local demo data only.
UPDATE system_sms_channel SET status = 1;
UPDATE system_social_client SET status = 1;
