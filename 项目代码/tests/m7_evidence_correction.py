"""Disclose one historical nested output-name collision; never fabricate restore."""
from datetime import datetime,timezone
import m7_support as h
p=h.OUT/'M4.2-clean-binding.json';current=h.load(p.name)
assert current['database'].startswith('fulfillment_m7_reg_returns_') and current['result']=='passed'
target='M7.2-returns-binding.json'
if not (h.OUT/target).exists():(h.OUT/target).write_bytes(p.read_bytes())
notice={'recorded_at':datetime.now(timezone.utc).isoformat(),'affected_file':p.name,'current_run_database':current['database'],'current_result_copy':target,'cause':'Historical return suite sets M1_EVIDENCE to a literal nested filename. Initial M7 AST replacement covered expiry but omitted this separate return filename.','historical_raw_restored':False,'boundary':'Original nested M4.2 raw JSON is unavailable locally after overwrite. No reconstruction is represented as historical evidence. Original main M4.2 acceptance/upgrade/restart reports remain separate.','fix':'Controlled filename replacement added; current passed68 binding result copied to M7-specific file; historical-path JSON explicitly marked as current M7 evidence.'}
h.save('M7-evidence-exception.json',notice)
current={'provenance_warning':notice,**current};h.save(p.name,current)
print('Current M7 nested evidence copied; historical overwrite exception disclosed')
