"""Main M6 seeded demo via HTTP. Adds ERP drafts only; never stock writes."""
import csv,hashlib,io,json,os,uuid
from datetime import datetime,timezone
import m6_foundation as m
os.environ['DB_NAME']='fulfillment';m.DATABASE='fulfillment'
E={'run_at':datetime.now(timezone.utc).isoformat(),'checks':[]}
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
def digest():return hashlib.sha256(json.dumps(m.business(),default=str,sort_keys=True).encode()).hexdigest()
try:
    check('main history includes V7',m.sql('SELECT MAX(CAST(version AS UNSIGNED)) FROM ful_flyway_schema_history')[0][0]==7)
    old=json.loads((m.ROOT/'../学习资料/10-验收证据/M5-main-demo.json').read_text(encoding='utf-8'));fx=old['fixture'];customer=m.sql('SELECT customer_id FROM erp_sale_order WHERE id=%s',(fx['source'],))[0][0];code=m.sql('SELECT bar_code FROM erp_product WHERE id=%s',(fx['product'],))[0][0]
    source='MAIN_M6_'+uuid.uuid4().hex[:8];out=io.StringIO(newline='');writer=csv.writer(out);writer.writerow(['externalOrderNo','customerCode','productCode','quantity','unitPrice']);writer.writerows([[source+'A',customer,code,'1.000001','2.345678'],[source+'B',customer,code,'2','2.345678'],[source+'Bad',customer,code,'0','2']]);data=('\ufeff'+out.getvalue()).encode('utf-8')
    (m.ROOT/'../学习资料/10-验收证据/M6-demo-input.csv').write_bytes(data);c=m.Client(48080).login();file=c.upload(data);key='demo-import-'+source;imported=c.import_file(file['fileId'],source,key);m.wait(lambda:m.state(imported['jobId'])[0]=='PARTIAL_FAILED')
    row=c.job(imported['jobId']);check('two real draft rows and one localized error',row['successRows']==2 and row['failedRows']==1 and row['hasErrors'])
    ekey='demo-export-'+source;exported=c.export('STOCK',[fx['warehouse']],ekey);m.wait(lambda:m.state(exported['jobId'])[0]=='SUCCEEDED');check('real scoped inventory workbook generated',c.job(exported['jobId'])['hasResult'])
    role=c.api('POST','/system/role/create',{'name':source+'仓库','code':source,'status':0,'sort':1});c.api('POST','/system/permission/assign-role-menu',{'roleId':role,'menuIds':[597,50019,50021,50024]});username='M6WH'+uuid.uuid4().hex[:8]
    uid=c.api('POST','/system/user/create',{'username':username,'nickname':'M6仓库演示','password':'admin123'});c.api('POST','/system/permission/assign-user-role',{'userId':uid,'roleIds':[role]})
    c.api('POST','/fulfillment/warehouse/grant',{'userId':str(uid),'warehouseId':str(fx['warehouse']),'permission':'READ','enabled':True,'reason':'M6演示账号仅查看指定仓库'},headers={'Idempotency-Key':uuid.uuid4().hex})
    E.update(source=source,file=file,import_key=key,import_result=imported,export_key=ekey,export_result=exported,warehouse_id=str(fx['warehouse']),warehouse_name=m.sql('SELECT name FROM erp_warehouse WHERE id=%s',(fx['warehouse'],))[0][0],warehouse_user_id=str(uid),warehouse_username=username,before_browser_digest=digest(),before_job_count=m.sql('SELECT COUNT(*) FROM ful_file_job')[0][0],before_download_count=m.sql("SELECT COUNT(*) FROM ful_operation_audit WHERE operation='FILE_DOWNLOAD'")[0][0])
    check('import creates exactly two unapproved drafts',m.sql('SELECT COUNT(*),MIN(o.status),MAX(o.status) FROM ful_import_identity i JOIN erp_sale_order o ON o.tenant_id=i.tenant_id AND o.id=i.erp_order_id WHERE i.source_system=%s',(source,))==((2,10,10),))
    E['result']='passed'
except Exception as error:E['result']='failed';E['error']=str(error);raise
finally:
    (m.ROOT/'../学习资料/10-验收证据/M6-main-demo.json').write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8');print(json.dumps(E,ensure_ascii=False,default=str),flush=True)
