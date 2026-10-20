"""Final artifact legacy ERP/binding regression plus mixed M5/M6 workers.
Own test vhost; never publishes isolated events into the main Broker vhost.
"""
import hashlib,io,csv,json,os,subprocess,sys,time,uuid
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import quote
import requests
ROOT=Path(__file__).resolve().parents[1]
core=json.loads((ROOT/'../学习资料/10-验收证据/M6-acceptance.json').read_text(encoding='utf-8'))
os.environ['M6_DATABASE']=core['database']
import m6_foundation as m
m.E={'run_at':datetime.now(timezone.utc).isoformat(),'database':m.DATABASE,'checks':[],'commands':[],'processes':[]};E=m.E
try:
    m.check('core passed exact final artifact',core['result']=='passed' and hashlib.sha256(m.JAR.read_bytes()).hexdigest()==core['artifact_sha256'])
    auth=('fulfillment','fulfillment-mq-dev');base='http://127.0.0.1:35673/api';vhost=quote(m.DATABASE,safe='')
    m.check('isolated mixed-worker vhost created',requests.put(base+'/vhosts/'+vhost,auth=auth,json={},timeout=10).status_code in [201,204])
    m.check('isolated vhost permissions assigned',requests.put(base+'/permissions/'+vhost+'/fulfillment',auth=auth,json={'configure':'.*','read':'.*','write':'.*'},timeout=10).status_code in [201,204])
    p=m.start('supplement-api',48082,options=('--fulfillment.jobs.tenant-pending-limit=20','--fulfillment.jobs.global-pending-limit=100'))
    env=os.environ.copy();env['API_BASE']='http://127.0.0.1:48082'
    for script,var,name in [('m1_acceptance.py','M1_EVIDENCE','M6-M1-regression.json'),('m0_smoke.py','M0_EVIDENCE','M6-ERP-regression.json')]:
        env[var]=name
        with (ROOT/'.local'/('m6-'+script+'.log')).open('wb') as out:r=subprocess.run([sys.executable,str(ROOT/'tests'/script)],env=env,stdout=out,stderr=subprocess.STDOUT,timeout=220)
        m.check('final legacy regression '+script,r.returncode==0)
    m.stop(p)
    mixed=m.start('mixed-workers',48082,True,('--fulfillment.messages.enabled=true','--fulfillment.messages.virtual-host='+m.DATABASE,'--fulfillment.messages.delay-ms=200','--fulfillment.jobs.tenant-pending-limit=20','--fulfillment.jobs.global-pending-limit=100','--fulfillment.jobs.batch-size=100'))
    c=m.Client(48082).login();fx=core['fixtures']['core'];customer=m.sql('SELECT customer_id FROM erp_sale_order WHERE id=%s',(fx['source'],))[0][0]
    before={t:m.sql('SELECT * FROM '+t+' ORDER BY id') for t in ['erp_stock','erp_stock_record','ful_order','ful_order_item','ful_reservation','ful_stock_ledger','ful_shipment','ful_shipment_item','ful_return','ful_return_item']}
    data=io.StringIO(newline='');writer=csv.writer(data);writer.writerow(['externalOrderNo','customerCode','productCode','quantity','unitPrice']);source='M6Mixed'+uuid.uuid4().hex[:8];writer.writerow([source,customer,core['product_code'],'1.000001','2.000001'])
    file=c.upload(data.getvalue().encode('utf-8'));job=c.import_file(file['fileId'],source)['jobId']
    m.wait(lambda:m.state(job)[0]=='SUCCEEDED',120)
    m.wait(lambda:m.sql("SELECT COUNT(*) FROM ful_outbox_event WHERE status<>'SENT'")[0][0]==0,150)
    m.wait(lambda:m.sql("SELECT COUNT(*) FROM ful_outbox_event o LEFT JOIN ful_inbox_event i ON i.tenant_id=o.tenant_id AND i.event_id=o.event_id WHERE i.id IS NULL OR i.status<>'PROCESSED'")[0][0]==0,150)
    m.check('M5 publication and Inbox converge while file worker succeeds',c.job(job)['successRows']==1 and m.sql("SELECT COUNT(*) FROM ful_outbox_event WHERE status='SENT'")[0][0]>0)
    m.check('mixed background work does not change stock or fulfillment facts',before=={t:m.sql('SELECT * FROM '+t+' ORDER BY id') for t in before})
    m.check('all execution read models current',not m.sql('SELECT o.id FROM ful_order o JOIN ful_outbox_event e ON e.tenant_id=o.tenant_id AND e.order_id=o.id LEFT JOIN ful_order_read_model r ON r.tenant_id=o.tenant_id AND r.order_id=o.id WHERE r.id IS NULL OR r.observed_version<>o.version'))
    E.update(artifact_sha256=core['artifact_sha256'],mixed_job=job,result='passed')
except Exception as error:E['result']='failed';E['error']=str(error);raise
finally:
    for p,out in m.OWNED:m.stop(p);out.close()
    E['all_owned_processes_stopped']=all(p.poll() is not None for p,_ in m.OWNED)
    (ROOT/'../学习资料/10-验收证据/M6-supplement.json').write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
    print('M6 supplement',E.get('result'),len(E['checks']),'checks',flush=True)
