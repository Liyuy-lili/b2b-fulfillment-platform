"""M6.2-M6.4 real HTTP/MySQL/private-file/two-JVM acceptance.
Uses the passed final-artifact M6.1 schema. All business/grants via APIs;
only documented private-file corruption and named-lock test barriers are injected.
"""
import concurrent.futures,csv,hashlib,io,json,os,shutil,socket,time,uuid,zipfile,xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
FOUNDATION=json.loads((ROOT/'../学习资料/10-验收证据/M6.1-foundation.json').read_text(encoding='utf-8'))
os.environ['M6_DATABASE']=FOUNDATION['database']
import m6_foundation as m
RUN='M6C'+uuid.uuid4().hex[:8]
E={'run_at':datetime.now(timezone.utc).isoformat(),'database':m.DATABASE,'redis_database':8,'checks':[],'commands':[],'processes':[],'fixtures':{},'injections':[]}
m.E=E
BASE=('--fulfillment.jobs.tenant-pending-limit=20','--fulfillment.jobs.global-pending-limit=100','--fulfillment.jobs.batch-size=100')
check=m.check;sql=m.sql;wait=m.wait;Client=m.Client
def start(label,worker=False,port=48083,options=()):return m.start('core-'+label,port,worker,BASE+tuple(options))
def csv_file(rows):
    out=io.StringIO(newline='');writer=csv.writer(out);writer.writerow(['externalOrderNo','customerCode','productCode','quantity','unitPrice']);writer.writerows(rows);return ('\ufeff'+out.getvalue()).encode('utf-8')
def submit(c,rows,source=None,key=None):
    file=c.upload(csv_file(rows));job=c.import_file(file['fileId'],source or RUN,key);return file,job['jobId']
def done(c,id,expected='SUCCEEDED',seconds=130):
    wait(lambda:m.state(id)[0] in ['SUCCEEDED','PARTIAL_FAILED','FAILED','CANCELLED'],seconds);result=c.job(id);check('task '+str(id)+' reaches '+expected,result['status']==expected,result);return result
def untouched():return {t:sql('SELECT * FROM '+t+' ORDER BY id') for t in ['erp_stock','erp_stock_record','ful_order','ful_order_item','ful_reservation','ful_stock_ledger','ful_shipment','ful_shipment_item','ful_cancellation','ful_return','ful_return_item','erp_sale_out','erp_sale_out_items','erp_sale_return','erp_sale_return_items']}
def identity(source):return sql('SELECT external_no,erp_order_id FROM ful_import_identity WHERE tenant_id=1 AND source_system=%s ORDER BY external_no',(source,))
def workbook(response):
    check('download is actual XLSX',response.status_code==200 and response.content.startswith(b'PK'))
    z=zipfile.ZipFile(io.BytesIO(response.content));ns={'x':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'};shared=[]
    if 'xl/sharedStrings.xml' in z.namelist():shared=[''.join(e.itertext()) for e in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('x:si',ns)]
    sheets=[]
    for filename in ['xl/worksheets/sheet1.xml','xl/worksheets/sheet2.xml']:
        root=ET.fromstring(z.read(filename));check('no generated formula cells '+filename,not root.findall('.//x:f',ns));rows=[]
        for row in root.findall('.//x:row',ns):
            values=[]
            for cell in row.findall('x:c',ns):
                v=cell.find('x:v',ns);value=v.text if v is not None else ''.join(t.text or '' for t in cell.findall('.//x:t',ns))
                if cell.get('t')=='s':value=shared[int(value)]
                values.append(value or '')
            rows.append(values)
        sheets.append(rows)
    return sheets
def normal_imports(c,f,fx):
    code=sql('SELECT bar_code FROM erp_product WHERE id=%s',(fx['product'],))[0][0];E['product_code']=code
    rows=[[RUN+'-valid',str(f.customer),code,'2.000001','3.000001'],[RUN+'-comma,quoted',str(f.customer),code,'1','2'],[RUN+'-zero',str(f.customer),code,'0','2'],[RUN+'-precision',str(f.customer),code,'1.0000001','2'],[RUN+'-sku',str(f.customer),'NOT-A-PRODUCT','1','2'],['=2+3',str(f.customer),code,'-1','2']]
    before=untouched();file,job=submit(c,rows,key='import-'+RUN);result=done(c,job,'PARTIAL_FAILED');E['imports']={'file':file,'job':job,'source':RUN,'rows':rows}
    check('two successful drafts and four independent row failures',result['totalRows']==6 and result['successRows']==2 and result['failedRows']==4 and result['pendingRows']==0)
    check('only valid rows create cross-task business identities',len(identity(RUN))==2)
    check('import drafts remain unapproved without automatic fulfillment',sql('SELECT DISTINCT o.status FROM erp_sale_order o JOIN ful_import_identity i ON i.tenant_id=o.tenant_id AND i.erp_order_id=o.id WHERE i.source_system=%s',(RUN,))==((10,),) and before==untouched())
    draft=identity(RUN)[0][1];check('import draft cannot bind without explicit approval',c.bind(draft,ok=False)['code']==1080000001)
    check('decimal quantity and price exact',sql('SELECT `count`,product_price FROM erp_sale_order_items WHERE order_id=(SELECT erp_order_id FROM ful_import_identity WHERE tenant_id=1 AND source_system=%s AND external_no=%s)',(RUN,RUN+'-valid'))[0]==(m.b.D('2.000001'),m.b.D('3.000001')))
    errors=c.download(job,'ERROR');parsed=list(csv.reader(io.StringIO(errors.content.decode('utf-8-sig'))));check('four real error rows and formula escaped',errors.status_code==200 and len(parsed)==5 and any(r[1]=="'=2+3" for r in parsed[1:]))
    repeat_file=c.upload(csv_file(rows));check('identical reupload same submission key returns original task',repeat_file['sha256']==file['sha256'] and c.import_file(repeat_file['fileId'],RUN,'import-'+RUN)['jobId']==job)
    second=c.import_file(repeat_file['fileId'],RUN)['jobId'];done(c,second,'PARTIAL_FAILED');check('new task same business rows reuses original drafts',len(identity(RUN))==2 and sql("SELECT DISTINCT outcome FROM ful_file_job_row WHERE job_id=%s AND status='SUCCEEDED'",(second,))==(('EXISTING',),))
    _,changed=submit(c,[[RUN+'-valid',str(f.customer),code,'3','3.000001']],RUN);done(c,changed,'PARTIAL_FAILED');check('changed content same external identity rejected',sql('SELECT error_code FROM ful_file_job_row WHERE job_id=%s',(changed,))==(('EXTERNAL_ORDER_CONTENT_CONFLICT',),) and len(identity(RUN))==2)
    return code
def import_faults(c,f,code,worker):
    m.stop(worker);source=RUN+'Fault';rows=[[source+'-'+str(n),str(f.customer),code,'1','2'] for n in range(3)];_,job=submit(c,rows,source)
    before=untouched();bad=start('row-failure',True,options=('--fulfillment.test.job-business-failure=true','--fulfillment.test.job-target='+job,'--fulfillment.jobs.max-attempts=1'))
    done(c,job,'FAILED');check('ERP-after-write fault rolls back order identity and row result',not identity(source) and sql("SELECT success_rows FROM ful_file_job WHERE id=%s",(job,))==((0,),) and before==untouched());m.stop(bad)
    healthy=start('row-retry',True);key='retry-'+RUN;request=c.control(job,True,key);done(c,job);check('healthy manual retry creates exactly three drafts',len(identity(source))==3);check('successful recovery request result immutable',c.control(job,True,key)==request);m.stop(healthy)
    source=RUN+'Crash';rows=[[source+'-'+str(n),str(f.customer),code,'1','2'] for n in range(3)];_,job=submit(c,rows,source);E['fixtures']['row_crash']={'job':job,'source':source}
    crash=start('row-crash',True,options=('--fulfillment.test.job-crash=AFTER_ROW','--fulfillment.test.job-target='+job));wait(lambda:crash.poll() is not None)
    check('real exit81 after first row commit',crash.returncode==81 and sql('SELECT success_rows FROM ful_file_job WHERE id=%s',(job,))==((1,),) and len(identity(source))==1)
    recovery=start('row-recovery',True);done(c,job);check('committed first row skipped after process restart',len(identity(source))==3 and c.job(job)['totalAttempts']==2 and before==untouched());m.stop(recovery)
    # A real boundary after row commit: request cancellation without a SQL state edit.
    source=RUN+'Cancel';rows=[[source+'-'+str(n),str(f.customer),code,'1','2'] for n in range(3)];_,job=submit(c,rows,source);E['fixtures']['cancelled']={'job':job,'source':source}
    with m.db() as lock:
        with lock.cursor() as cur:cur.execute('SELECT GET_LOCK(%s,0)',('m6row:'+m.DATABASE,));check('own after-row test barrier',cur.fetchone()[0]==1)
        try:
            paused=start('row-cancel',True,options=('--fulfillment.test.job-row-barrier=true','--fulfillment.test.job-target='+job))
            wait(lambda:'M6_BARRIER_ROW' in (ROOT/'.local/m6-core-row-cancel-out.log').read_text(encoding='utf-8',errors='replace'))
            check('one row durably committed before cancellation',sql('SELECT success_rows FROM ful_file_job WHERE id=%s',(job,))==((1,),))
            key='cancel-running-'+RUN;cancel=c.control(job,key=key);check('running cancel is persistent request',cancel['outcome']=='CANCEL_REQUESTED')
            with lock.cursor() as cur:cur.execute('SELECT RELEASE_LOCK(%s)',('m6row:'+m.DATABASE,))
            result=done(c,job,'CANCELLED');check('cancel preserves one committed draft and two pending rows',result['successRows']==1 and result['pendingRows']==2 and len(identity(source))==1)
            check('cancel request key stable after worker completion',c.control(job,key=key)==cancel)
            check('cancelled task cannot be retried as failed task',c.control(job,True,ok=False)['code']==1080000072);m.stop(paused)
        finally:
            with lock.cursor() as cur:cur.execute('SELECT RELEASE_ALL_LOCKS()')
    # Corrupt only a private file in this isolated schema, then restore it.
    file,job=submit(c,[[RUN+'Tamper',str(f.customer),code,'1','2']],RUN+'Tamper');meta=sql('SELECT storage_key FROM ful_private_file WHERE id=%s',(file['fileId'],))[0][0]
    root=(ROOT/'.local/fulfillment-files'/m.DATABASE).resolve();path=(root/meta).resolve();check('tamper fixture remains inside private test directory',path.parent==root)
    original=path.read_bytes()
    try:
        path.write_bytes(original+b'\n');E['injections'].append({'kind':'private_input_tamper','file_id':file['fileId'],'restored':False})
        healthy=start('limits',True);done(c,job,'FAILED');check('input hash mismatch creates no draft',not identity(RUN+'Tamper'))
    finally:path.write_bytes(original);E['injections'][-1]['restored']=True
    # Limits exercised against the actual default 10MiB and 10000-row boundaries.
    count=sql('SELECT COUNT(*) FROM ful_private_file')[0][0];check('10MiB plus one upload rejected',c.upload(b'x'*10485761,ok=False)['code']==1080000073);check('rejected upload leaves no file metadata',sql('SELECT COUNT(*) FROM ful_private_file')[0][0]==count)
    check('wrong input extension rejected',c.upload(b'not-excel','input.xlsx',False)['code']==1080000073)
    large=[[RUN+'Big'+str(n),str(f.customer),code,'1','2'] for n in range(10001)];_,too_many=submit(c,large,RUN+'Big');result=done(c,too_many,'FAILED',180)
    check('10001 rows rejected before any ERP side effect',not result['prepared'] and result['successRows']==0 and result['lastError']=='IMPORT_ROW_LIMIT' and not identity(RUN+'Big'))
    file=c.upload(b'wrong,header\r\n');invalid=c.import_file(file['fileId'],RUN+'Header')['jobId'];done(c,invalid,'FAILED');check('invalid header has no partial business effect',not identity(RUN+'Header') and before==untouched())
    file=c.upload(bytes([0xc3,0x28]));utf=c.import_file(file['fileId'],RUN+'Utf8')['jobId'];result=done(c,utf,'FAILED');check('invalid UTF8 stops once without business effects',result['totalAttempts']==1 and not identity(RUN+'Utf8'))
    return healthy

def ship_existing(c,f,fx,label,quantity='1'):
    source=c.create('sale-order',{'customerId':f.customer,'accountId':f.account,'orderTime':m.b.NOW,'discountPercent':'0','items':[{'productId':fx['product'],'count':quantity,'productPrice':'2','taxPercent':'0'}]});c.approve('sale-order',source)
    order=c.bind(source)['orderId'];held=c.allocate(order,[f.w])['reservations'][0]
    shipment=c.ship(order,f.w,[(held['id'],quantity)]);return {'source':source,'order':order,'shipment':shipment['shipmentId']}

def export_and_authorization(c,f,fx,worker,api):
    m.stop(worker)
    # At least two rows in one warehouse ensure the 1-row export chunks move a cursor.
    extra=ship_existing(c,f,fx,'before');key='export-freeze-'+RUN
    export=c.export('SHIPMENT',[f.w],key);maximum=sql('SELECT max_source_id FROM ful_file_job WHERE id=%s',(export['jobId'],))[0][0]
    future=ship_existing(c,f,fx,'after');E['fixtures']['export_after_submission']=future
    before=untouched();worker=start('export-normal',True,options=('--fulfillment.jobs.batch-size=1',));done(c,export['jobId'])
    data,description=workbook(c.download(export['jobId']));orders=[r[2] for r in data[1:]]
    check('export frozen max ID excludes newly created shipment',extra['order'] in orders and future['order'] not in orders and int(c.job(export['jobId'])['sourceCursor'])<=maximum)
    check('actual data exported in multiple cursor chunks',len(data[1:])>=2 and len(orders)==len(set(orders)))
    check('XLSX declares generation window and non-snapshot boundary',any('非严格时点快照' in str(r) for r in description) and any('生成开始' in str(r) for r in description) and any('生成结束' in str(r) for r in description))
    check('all export work leaves business facts unchanged',before==untouched());E['exports']={'job':export,'key':key,'maximum':maximum};m.stop(worker)
    cap=c.export('SHIPMENT',[f.w])['jobId'];limited=start('export-limit',True,options=('--fulfillment.jobs.export-max-rows=1','--fulfillment.jobs.batch-size=1'))
    result=done(c,cap,'FAILED');check('export limit never publishes partial workbook',not result['hasResult'] and result['lastError']=='EXPORT_ROW_LIMIT' and before==untouched());m.stop(limited)
    # Old worker has already generated its private file; a second JVM recovers
    # the expired lease and publishes the only authorized file reference.
    fenced=c.export('STOCK',[f.w])['jobId'];E['fixtures']['fenced_export']=fenced
    with m.db() as lock:
        with lock.cursor() as cur:cur.execute('SELECT GET_LOCK(%s,0)',('m6publish:'+m.DATABASE,));check('own artifact publish barrier',cur.fetchone()[0]==1)
        try:
            paused=start('export-fence-old',True,options=('--fulfillment.test.job-publish-barrier=true','--fulfillment.test.job-target='+fenced,))
            wait(lambda:'M6_BARRIER_PUBLISH' in (ROOT/'.local/m6-core-export-fence-old-out.log').read_text(encoding='utf-8',errors='replace'));old=m.state(fenced)[1]
            m.stop(api);api=start('export-fence-new',True,48082);c=Client(48082).login();done(c,fenced)
            saved=sql('SELECT status,lease_version,result_file_id,source_cursor FROM ful_file_job WHERE id=%s',(fenced,));check('second JVM publishes higher lease generation',saved[0][1]>old)
            with lock.cursor() as cur:cur.execute('SELECT RELEASE_LOCK(%s)',('m6publish:'+m.DATABASE,))
            wait(lambda:'Job stale worker ignored job='+fenced in (ROOT/'.local/m6-core-export-fence-old-out.log').read_text(encoding='utf-8',errors='replace'))
            check('old artifact cannot overwrite new file reference or progress',sql('SELECT status,lease_version,result_file_id,source_cursor FROM ful_file_job WHERE id=%s',(fenced,))==saved and before==untouched())
            check('two actual lease owners in publication race',sql("SELECT COUNT(DISTINCT JSON_UNQUOTE(JSON_EXTRACT(after_json,'$.owner'))) FROM ful_operation_audit WHERE object_type='JOB' AND object_id=%s AND operation='JOB_CLAIM'",(fenced,))[0][0]==2)
            m.stop(paused);m.stop(api)
        finally:
            with lock.cursor() as cur:cur.execute('SELECT RELEASE_ALL_LOCKS()')
    api=start('permission-api',port=48082);c=Client(48082).login();worker=start('permission-worker',True)
    permission_cases(c,f,fx,worker)
    # No worker remains after permission/context tests. Verify saved intent keys.
    m.stop(api);api=start('restart-api',port=48082);c=Client(48082).login();count=sql('SELECT COUNT(*) FROM ful_file_job')[0][0]
    original=E['imports'];check('import request key stable after JVM restart',c.import_file(original['file']['fileId'],original['source'],'import-'+RUN)['jobId']==original['job'])
    check('export request key stable after JVM restart',c.export('SHIPMENT',[f.w],key)==export)
    check('saved request replay creates no new job',sql('SELECT COUNT(*) FROM ful_file_job')[0][0]==count)
    report=c.api('POST','/fulfillment/reconcile/run',{'scope':'TENANT'},headers={'Idempotency-Key':uuid.uuid4().hex});check('final inventory and fulfillment reconciliation clean',report['differenceCount']==0,report)
    E['final_counts']={table:sql('SELECT COUNT(*) FROM '+table)[0][0] for table in ['ful_private_file','ful_file_job','ful_file_job_row','ful_import_identity','ful_operation_audit','ful_warehouse_grant']}

def role_user(c,label,menus):
    role=c.api('POST','/system/role/create',{'name':RUN+label,'code':RUN+label,'status':0,'sort':1});c.api('POST','/system/permission/assign-role-menu',{'roleId':role,'menuIds':menus})
    name=RUN+label;uid=c.api('POST','/system/user/create',{'username':name,'nickname':name,'password':'admin123'});c.api('POST','/system/permission/assign-user-role',{'userId':uid,'roleIds':[role]})
    return uid,role,Client(48082).login(name)
def grant(c,user,warehouse,permission='READ',enabled=True,key=None,ok=True):return c.api('POST','/fulfillment/warehouse/grant',{'userId':str(user),'warehouseId':str(warehouse),'permission':permission,'enabled':enabled,'reason':'M6权限与撤销验证'},headers={'Idempotency-Key':key or uuid.uuid4().hex},ok=ok)
def permission_cases(c,f,fx,worker):
    uid,role,user=role_user(c,'Warehouse',[597,50019,50021,50024]);E['fixtures']['warehouse_user']=uid
    check('ordinary user begins with no default warehouse access',user.api('GET','/fulfillment/warehouse/scope')==[])
    key='grant-'+RUN;applied=grant(c,uid,f.w,key=key);check('warehouse grant idempotent',grant(c,uid,f.w,key=key)==applied)
    check('warehouse read scope explicit and string identifiers',user.api('GET','/fulfillment/warehouse/scope')==[{'id':str(f.w),'name':sql('SELECT name FROM erp_warehouse WHERE id=%s',(f.w,))[0][0],'canOperate':False}])
    view=user.api('GET','/fulfillment/warehouse/stock-page',params={'warehouseId':f.w});check('warehouse stock projection has no financial or customer fields',view['list'] and all(set(r)=={'id','productId','warehouseId','physical','reserved','available'} for r in view['list']))
    shipment=user.api('GET','/fulfillment/warehouse/shipment-get',params={'id':fx['shipment']});check('warehouse detail excludes prices customer and other warehouse items',set(shipment)=={'id','shipmentNo','orderId','warehouseId','status','shippedAt','items'} and all(set(i)=={'id','productId','quantity'} for i in shipment['items']))
    check('warehouse-only role cannot request full priced order',user.api('GET','/fulfillment/order/get',params={'id':fx['order']},ok=False)['code']==403)
    check('warehouse-only role cannot request broad ERP customer data',user.api('GET','/erp/customer/get',params={'id':f.customer},ok=False)['code']==403)
    wh2=c.create('warehouse',{'name':RUN+'第二仓','status':0,'sort':1,'warehousePrice':'0','truckagePrice':'0'});inc=c.create('stock-in',{'supplierId':f.supplier,'inTime':m.b.NOW,'items':[{'productId':fx['product'],'warehouseId':wh2,'count':'5','productPrice':'0'}]});c.approve('stock-in',inc)
    check('unauthorized warehouse explicitly rejected',user.api('GET','/fulfillment/warehouse/stock-page',params={'warehouseId':wh2},ok=False)['code']==1080000075)
    export_key='user-export-'+RUN;job=user.export(key=export_key)['jobId'];done(c,job);data,_=workbook(user.download(job));check('warehouse export excludes prices and customer fields',data[0]==['商品编号','仓库编号','实物H','预占R','可用A'])
    grant(c,uid,wh2);check('new grant does not broaden old all-current submission key',user.export(key=export_key)['jobId']==job)
    check('frozen warehouse list stays original',json.loads(sql('SELECT scope_json FROM ful_file_job WHERE id=%s',(job,))[0][0])['warehouseIds']==[f.w] and all(r[1]==str(f.w) for r in data[1:]))
    grant(c,uid,f.w,enabled=False);check('download rechecks revoked warehouse range',user.download(job).json()['code']==1080000074)
    check('old successful export key rechecks current scope',user.export(key=export_key,ok=False)['code']==1080000074)
    check('other actor task identity hidden',user.job(E['imports']['job'],False)['code']==1080000070)
    page=user.api('GET','/fulfillment/job/page');check('ordinary task page contains own actor only',all(r['actorId']==str(uid) for r in page['list']))
    check('page sizes bounded',c.api('GET','/fulfillment/job/page',params={'pageSize':51},ok=False)['code']==400)
    menus=[r[0] for r in sql("SELECT id FROM system_menu WHERE deleted=0 AND (permission LIKE 'erp:%%' OR permission LIKE 'fulfillment:%%' OR id=597)")]
    sales_id,sales_role,sales=role_user(c,'Sales',menus);sf=m.b.Fixture(sales,'Sales');grant(c,sales_id,sf.w,'OPERATE');sfx=sf.shipment('权限闭环',('1',),ordered='3');E['fixtures']['sales']=sfx
    create_key='return-create-'+RUN;receive_key='return-receive-'+RUN;ret=sales.create_return(sfx['order'],sfx['shipment'],[(sfx['lines'][0]['id'],'1')],create_key);sales.receive(sfx['order'],ret['id'],receive_key)
    # Release on a second order creates an original successful key for revocation replay.
    source=sales.create('sale-order',{'customerId':sf.customer,'accountId':sf.account,'orderTime':m.b.NOW,'items':[{'productId':sfx['product'],'count':'1','productPrice':'2','taxPercent':'0'}]});sales.approve('sale-order',source);order=sales.bind(source)['orderId'];held=sales.allocate(order,[sf.w])['reservations'][0];release_key='release-'+RUN;sales.release(order,[(held['id'],'1')],release_key)
    allocate_key=sql("SELECT idempotency_key FROM ful_command_record WHERE actor_id=%s AND command_type='ALLOCATE' ORDER BY id DESC LIMIT 1",(sales_id,))[0][0]
    ship_key=sql("SELECT idempotency_key FROM ful_command_record WHERE actor_id=%s AND command_type='SHIP' ORDER BY id DESC LIMIT 1",(sales_id,))[0][0]
    cancel_key=sql("SELECT idempotency_key FROM ful_command_record WHERE actor_id=%s AND command_type='CANCEL' ORDER BY id DESC LIMIT 1",(sales_id,))[0][0]
    grant(c,sales_id,sf.w,'READ');grant(c,sales_id,sf.w,'OPERATE',False);before=untouched()
    check('revoked operation blocks original successful allocate key',sales.allocate(order,[sf.w],key=allocate_key,ok=False)['code']==1080000075)
    check('revoked operation blocks original successful release key',sales.release(order,[(held['id'],'1')],release_key,False)['code']==1080000075)
    check('revoked operation blocks original successful shipment key',sales.ship(sfx['order'],sf.w,[(sfx['lines'][0]['reservationId'],'1')],ship_key,False)['code']==1080000075)
    item=sales.api('GET','/fulfillment/order/get',params={'id':sfx['order']})['items'][0]
    check('revoked operation blocks original successful cancel key',sales.cancel(sfx['order'],[(item['id'],'2')],cancel_key,False)['code']==1080000075)
    check('revoked operation blocks original successful return receipt key',sales.receive(sfx['order'],ret['id'],receive_key,False)['code']==1080000075)
    check('read grant still allows scoped inventory',sales.api('GET','/fulfillment/stock/get',params={'warehouseId':sf.w,'productId':sfx['product']})['warehouseId']==str(sf.w))
    check('legacy stock entry checks warehouse range',sales.api('GET','/fulfillment/stock/get',params={'warehouseId':wh2,'productId':sfx['product']},ok=False)['code']==1080000075)
    check('functional grant permission alone cannot self-escalate warehouse data',grant(sales,sales_id,wh2,'OPERATE',ok=False)['code']==403)
    check('denied actions and successful old-key replays change no business facts',before==untouched())
    check('full sales function still cannot read other owners order',sales.api('GET','/fulfillment/order/get',params={'id':fx['order']},ok=False)['code']==1080000003)
    check('known file from another actor cannot be used for import',sales.import_file(E['imports']['file']['fileId'],RUN+'Steal',ok=False)['code']==1080000073)
    m.stop(worker)
    tenant_context_cases(c,f,fx,sales,sales_id,menus)

def tenant_context_cases(c,f,fx,sales,sales_id,menus):
    package=c.api('POST','/system/tenant-package/create',{'name':RUN,'status':0,'menuIds':menus})
    tenant=c.api('POST','/system/tenant/create',{'name':RUN+'租户','contactName':'M6','status':0,'packageId':package,'expireTime':'2035-12-31T23:59:59','accountCount':10,'username':RUN+'Tenant','password':'admin123','websites':[]})
    foreign=Client(48082,tenant).login(RUN+'Tenant');ff=m.b.Fixture(foreign,'Tenant');ffx=ff.shipment('线程隔离',('1',));E['fixtures']['foreign']={'tenant':tenant,**ffx}
    code=sql('SELECT bar_code FROM erp_product WHERE id=%s',(ffx['product'],))[0][0];source=RUN+'Ctx'
    foreign_file,foreign_job=submit(foreign,[['COMMON-EXTERNAL',str(ff.customer),code,'1','2']],source)
    root_file,root_job=submit(c,[['COMMON-EXTERNAL',str(f.customer),E['product_code'],'1','2']],source)
    disabled_file,disabled_job=submit(sales,[[RUN+'Disabled',str(f.customer),E['product_code'],'1','2']],RUN+'Disabled')
    c.api('PUT','/system/user/update-status',{'id':sales_id,'status':1})
    worker=start('context-worker',True);done(c,root_job);done(foreign,foreign_job);done(c,disabled_job,'FAILED')
    check('disabled original actor creates no draft',not identity(RUN+'Disabled') and c.job(disabled_job)['lastError']=='ACTOR_DISABLED')
    check('tenant-separated business identity and ERP creator preserved',sql('SELECT COUNT(*),COUNT(DISTINCT i.tenant_id) FROM ful_import_identity i JOIN erp_sale_order o ON o.tenant_id=i.tenant_id AND o.id=i.erp_order_id WHERE i.source_system=%s AND CAST(o.creator AS UNSIGNED)=i.actor_id',(source,))==((2,2),))
    logs=(ROOT/'.local/m6-core-context-worker-out.log').read_text(encoding='utf-8',errors='replace')
    clear=[line.split('thread=',1)[1] for line in logs.splitlines() if 'M6_CONTEXT_CLEAR thread=' in line]
    check('one actual reused worker thread clears tenant and actor contexts',len(clear)>=3 and all('tenant=null actor=null' in line for line in clear) and len({line.split(' tenant=')[0] for line in clear})==1,clear)
    check('foreign tenant cannot get known task',foreign.job(root_job,False)['code']==1080000070)
    check('tenant one cannot get foreign task',c.job(foreign_job,False)['code']==1080000070)
    check('foreign input file cannot be imported by known ID',c.import_file(foreign_file['fileId'],RUN+'ForeignSteal',ok=False)['code']==1080000073)
    check('foreign warehouse ID denied even to tenant admin',foreign.api('GET','/fulfillment/warehouse/stock-page',params={'warehouseId':f.w},ok=False)['code']==1080000075)
    check('foreign shipment ID hidden',c.api('GET','/fulfillment/warehouse/shipment-get',params={'id':ffx['shipment']},ok=False)['code']==1080000022)
    check('grant cannot cross tenant user identity',grant(c,sql('SELECT id FROM system_users WHERE tenant_id=%s AND username=%s',(tenant,RUN+'Tenant'))[0][0],f.w,ok=False)['code']==1080000075)
    check('administrator download also checks disabled originator',c.download(disabled_job,'INPUT').json()['code']==1080000074)
    runtime=Client(48083).login().api('GET','/fulfillment/job/runtime')['instance'];check('actual worker and queued counts remain bounded',runtime['active']<=1 and runtime['queued']<=1 and runtime['workers']==runtime['queueCapacity']==1,runtime)
    E['fixtures']['context']={'root_job':root_job,'foreign_job':foreign_job,'disabled_job':disabled_job};m.stop(worker)

def main():
    check('passed final-artifact foundation first',FOUNDATION['result']=='passed' and FOUNDATION['all_owned_processes_stopped'] and hashlib.sha256(m.JAR.read_bytes()).hexdigest()==FOUNDATION['artifact_sha256'])
    api=start('api',port=48082);c=Client(48082).login();f=m.b.Fixture(c,'Core');fx=f.shipment('导入导出',('1',));E['fixtures']['core']=fx
    worker=start('normal',True);code=normal_imports(c,f,fx);worker=import_faults(c,f,code,worker)
    export_and_authorization(c,f,fx,worker,api)
    E['artifact_sha256']=FOUNDATION['artifact_sha256'];E['result']='passed'

if __name__=='__main__':
    try:main()
    except Exception as error:E['result']='failed';E['error']=str(error);raise
    finally:
        for p,out in m.OWNED:m.stop(p);out.close()
        E['all_owned_processes_stopped']=all(p.poll() is not None for p,_ in m.OWNED)
        prefix='M6-' if E.get('result')=='passed' else 'M6-failed-'+RUN+'-'
        for p in (ROOT/'.local').glob('m6-core-*-out.log'):shutil.copyfile(p,ROOT/'../学习资料/10-验收证据'/(prefix+p.name))
        (ROOT/'../学习资料/10-验收证据'/('M6-acceptance.json' if E.get('result')=='passed' else prefix+'result.json')).write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
        print('M6 core',E.get('result'),len(E['checks']),'checks',flush=True)
