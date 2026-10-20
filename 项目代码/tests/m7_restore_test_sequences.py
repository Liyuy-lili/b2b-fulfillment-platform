"""Repair only DB12 counters for the retained M7 foundation fixture schema."""
import hashlib,importlib.util,json,os
from datetime import datetime,timezone
import m7_support as h
DB=h.load('M7.2-filefoundation.json')['database'];assert DB.startswith('fulfillment_m7_reg_filefoundation_')
assert all(h.free(p) for p in [48082,48083,48084]);os.environ['REDIS_DATABASE']='12'
spec=importlib.util.spec_from_file_location('m7_seq_tools',h.ROOT/'scripts/repair_erp_sequences.py');seq=importlib.util.module_from_spec(spec);spec.loader.exec_module(seq)
q=lambda s,a=():h.sql(DB,s,a)
def facts():
    tables=q("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND (LEFT(TABLE_NAME,4)='erp_' OR LEFT(TABLE_NAME,4)='ful_') ORDER BY TABLE_NAME")
    return hashlib.sha256(json.dumps({t[0]:q('SELECT * FROM '+t[0]+' ORDER BY '+('installed_rank' if t[0]=='ful_flyway_schema_history' else 'tenant_id' if t[0]=='ful_job_gate' else 'id')) for t in tables},default=str,sort_keys=True).encode()).hexdigest()
E={'run_at':datetime.now(timezone.utc).isoformat(),'database':DB,'redis_database':12,'rows':[],'cause':'Initial orchestrator flushed DB12 between filefoundation and file although they share SQL data. ERP correctly rejected a duplicate stock-in number.','boundary':'No main DB0, no business SQL writes; raise test-only counters from all existing SQL numbers including deleted/all tenants.'};before=facts()
for prefix,table in seq.TABLES.items():
    no_prefix=prefix+datetime.now().strftime('%Y%m%d');key='erp:seq_no:'+no_prefix
    maximum=int(q('SELECT COALESCE(MAX(CAST(SUBSTRING(no,%s) AS UNSIGNED)),0) FROM '+table+' WHERE no REGEXP %s',(len(no_prefix)+1,'^'+no_prefix+'[0-9]{6,}$'))[0][0]);old=seq.redis('GET',key)
    new=seq.redis('EVAL',"local n=tonumber(redis.call('GET',KEYS[1]) or '0'); local m=tonumber(ARGV[1]); if m>n then redis.call('SET',KEYS[1],m,'EX',86400); return m; end; return n;",1,key,maximum)
    assert new>=maximum and new>=int(old or 0);E['rows'].append({'key':key,'before':old,'sql_max':maximum,'after':new})
E.update(before_fact_sha256=before,after_fact_sha256=facts());assert E['before_fact_sha256']==E['after_fact_sha256'];E['result']='passed';h.save('M7.2-sequence-repair.json',E);print('Test DB12 counters raised; all SQL facts unchanged')
