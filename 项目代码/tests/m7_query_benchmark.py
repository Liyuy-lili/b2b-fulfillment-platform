"""Same HTTP/data/JVM, alternating invisible/visible new index, warmed rounds."""
import hashlib,json,os,threading,time,uuid,zipfile,io
from datetime import datetime,timezone
import requests,psutil
import m7_support as h
from m7_perf_tools import Sample,parallel,digest_stats,delta_stats,root_sql,cpu_model
prep=h.load('M7.3-query-prepare.json');assert prep['result']=='passed';DB=prep['database'];rt=h.Runtime(DB,10);INDEX='ix_order_tenant_deleted_status_id'
E={'run_at':datetime.now(timezone.utc).isoformat(),'database':DB,'artifact_sha256':h.sha(h.JAR),'checks':[],'rounds':[],'exports':[],'boundary':'Single Windows host, one 768MiB JVM, local HTTP client and MySQL. Synthetic query dataset, warmed alternating index visibility, no production throughput claim.'}
q=lambda s,a=():h.sql(DB,s,a)
def check(name,ok,detail=None):
    E['checks'].append(dict(name=name,passed=bool(ok),detail=detail));print(('PASS ' if ok else 'FAIL ')+name,flush=True);assert ok,name
def fixture_digest():return hashlib.sha256(json.dumps(q('SELECT tenant_id,status,COUNT(*),SUM(version),SUM(total_price) FROM ful_order GROUP BY tenant_id,status'),default=str).encode()).hexdigest()
try:
    check('all regression suites complete before timed benchmark',all(h.load('M7.2-'+c+'-run.json')['result']=='passed' for c in ['core','expiry','returns','reconcile','message','filefoundation','file']))
    p=rt.start(48085,'query-benchmark',{'fulfillment.jobs.enabled':'true'});admin=h.Client(48085).login();headers=dict(admin.s.headers);local=threading.local()
    E['environment']={'cpu':os.environ.get('PROCESSOR_IDENTIFIER'),'logical_processors':os.cpu_count(),'ram_bytes':psutil.virtual_memory().total,'jvm_args':['-Xms128m','-Xmx768m'],'instances':1,'druid_max_active':12,'mysql':q('SELECT VERSION(),@@innodb_buffer_pool_size,@@transaction_isolation'),'requests_per_phase':96,'concurrency':[4,8],'rounds':3,'warmup_requests':20,'mix':'WAIT_STOCK status, page1/page80 50:50, pageSize50; authenticated tenant1 admin; login/setup excluded','datasets':q('SELECT tenant_id,status,COUNT(*) FROM ful_order GROUP BY tenant_id,status')}
    E['environment'].update(cpu_model=cpu_model(),physical_cores=psutil.cpu_count(logical=False),mysql_tuple_columns=['version','innodb_buffer_pool_size','probe_connection_isolation_not_application'],application_write_isolation='READ_COMMITTED; startup verified',cpu_metric='100 percent equals one fully used CPU core; not divided by logical processor count')
    before=fixture_digest();expected={n:[str(r[0]) for r in q('SELECT id FROM ful_order WHERE tenant_id=1 AND deleted=0 AND status=%s ORDER BY id DESC LIMIT %s,50',('WAIT_STOCK',(n-1)*50))] for n in [1,80]}
    def request(n):
        if not hasattr(local,'session'):local.session=requests.Session();local.session.headers.update(headers)
        page=[1,80][n%2];response=local.session.get('http://127.0.0.1:48085/admin-api/fulfillment/order/page',params={'status':'WAIT_STOCK','pageNo':page,'pageSize':50},timeout=45);response.raise_for_status();body=response.json();assert body['code']==0,body
        data=body['data'];assert data['total']==5000 and [r['id'] for r in data['list']]==expected[page],data
        return {'page':page,'rows':len(data['list']),'total':data['total'],'http':response.status_code,'code':body['code']}
    E['plans']={}
    for round_ in range(3):
        for mode in (['before','after'] if round_%2==0 else ['after','before']):
            q('ALTER TABLE ful_order ALTER INDEX '+INDEX+(' INVISIBLE' if mode=='before' else ' VISIBLE'));q('ANALYZE TABLE ful_order')
            if mode not in E['plans']:
                E['plans'][mode]={}
                for page in [1,80]:
                    query='SELECT * FROM ful_order WHERE tenant_id=1 AND deleted=0 AND status=\'WAIT_STOCK\' ORDER BY id DESC LIMIT '+str((page-1)*50)+',50'
                    E['plans'][mode][str(page)]={'json':json.loads(q('EXPLAIN FORMAT=JSON '+query)[0][0]),'analyze':q('EXPLAIN ANALYZE '+query)[0][0]}
            for c in [4,8]:
                for n in range(20):request(n)
                stats=digest_stats(DB)
                with Sample(p.pid) as sample:rows,result=parallel(request,range(96),c)
                phase={'round':round_+1,'mode':mode,'concurrency':c,'summary':result,'requests':rows,'resources':sample.result,'sql_delta':delta_stats(stats,digest_stats(DB))};E['rounds'].append(phase)
                check('query round '+str(round_+1)+' '+mode+' c'+str(c),result['errors']==0,result);h.save('M7.3-query.json',E)
    # Two observations, not a statistically supported export speedup claim.
    for mode in ['before','after']:
        q('ALTER TABLE ful_order ALTER INDEX '+INDEX+(' INVISIBLE' if mode=='before' else ' VISIBLE'))
        with Sample(p.pid) as sample:
            t=time.perf_counter();job=admin.api('POST','/fulfillment/job/export',{'dataset':'ORDER','orderStatus':'NEW'},key='m7-export-'+mode+'-'+uuid.uuid4().hex)
            ident=job['jobId'];h.wait(lambda:admin.api('GET','/fulfillment/job/get',params={'id':ident})['status'] in ['SUCCEEDED','FAILED'],180)
            state=admin.api('GET','/fulfillment/job/get',params={'id':ident});check('full bounded ORDER export '+mode,state['status']=='SUCCEEDED',state)
            response=admin.s.get(admin.base+'/fulfillment/job/download',params={'id':ident,'kind':'RESULT'},timeout=90);response.raise_for_status();data=response.content;assert zipfile.is_zipfile(io.BytesIO(data));duration=time.perf_counter()-t
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            sheets=[n for n in z.namelist() if n.startswith('xl/worksheets/sheet') and n.endswith('.xml')];rows=sum(z.read(n).count(b'<row ') for n in sheets);assert all(b'<f>' not in z.read(n) for n in sheets)
        h.OUT.joinpath('M7.3-export-'+mode+'.xlsx').write_bytes(data);E['exports'].append({'mode':mode,'job_id':ident,'state':state,'seconds':duration,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'xlsx_rows_including_headers':rows,'resources':sample.result})
    # Cross-tenant API sampling uses real tenant-specific account and references.
    other=h.Client(48085,int(list(prep['tenants'])[1])).login('m7querytenant');other_rows=other.api('GET','/fulfillment/order/page',params={'status':'WAIT_STOCK','pageNo':1,'pageSize':50})
    check('other tenant sees own exact status count and disjoint IDs',other_rows['total']==5000 and not set(r['id'] for r in other_rows['list'])&set(expected[1]))
    check('benchmark does not change order facts',fixture_digest()==before);E['index_size_pages']=root_sql("SELECT stat_name,stat_value FROM mysql.innodb_index_stats WHERE database_name=%s AND table_name='ful_order' AND index_name=%s",(DB,INDEX));E['result']='passed'
except Exception as error:E.update(result='failed',error=str(error));raise
finally:
    q('ALTER TABLE ful_order ALTER INDEX '+INDEX+' VISIBLE');E['owned_stopped']=rt.close();h.save('M7.3-query.json',E)
    if E.get('result')=='failed':h.save('M7.3-query-failed-'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.json',E)
