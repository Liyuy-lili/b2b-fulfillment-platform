"""Verify the final artifact's added allowance query and legacy ERP path.
Reuses the isolated core database, preserving its evidence. Starts only owned JVMs.
"""
import hashlib,json,os,shutil,socket,subprocess,sys
from datetime import datetime,timezone
from decimal import Decimal as D
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
core=json.loads((ROOT/'../学习资料/10-验收证据/M4.2-return-acceptance.json').read_text(encoding='utf-8'))
os.environ['M4_RETURN_DATABASE']=core['database']
import m4_return_acceptance as base
from m1_acceptance import sql
E={'run_at':datetime.now(timezone.utc).isoformat(),'database':core['database'],'checks':[]}
def check(name,ok,detail=None):
    E['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
    if not ok:raise AssertionError(name+': '+str(detail))
base.check=check
try:
    check('core passed and its workers stopped',core['result']=='passed' and core['all_owned_processes_stopped'])
    with socket.socket() as s:check('test port free',s.connect_ex(('127.0.0.1',48082))!=0)
    E['core_artifact_sha256']=hashlib.sha256(base.JAR.read_bytes()).hexdigest()
    shutil.copyfile(ROOT/'backend/yudao-server/target/yudao-server.jar',base.JAR)
    E['final_artifact_sha256']=hashlib.sha256(base.JAR.read_bytes()).hexdigest()
    p=base.start('final-read',port=48082);c=base.Client(48082).login()
    fx=core['ids']['精度闭环']
    def allowance(client,fixture,ok=True):return client.api('GET','/fulfillment/return/allowance',params={'orderId':fixture['order'],'shipmentId':fixture['shipment']},ok=ok)
    value=allowance(c,fx)
    check('full received allowance excludes rejected applications',len(value)==1 and value[0]['shippedQty']=='6.000001' and value[0]['committedQty']=='6.000001' and value[0]['availableQty']=='0.000000',value)
    cf=core['ids']['并发申请'];v=allowance(c,cf)
    check('allowance sums pending and received exactly once',v[0]['committedQty']=='4.000000' and v[0]['availableQty']=='1.000000')
    multi=allowance(c,core['ids']['重复商品两行'])
    check('same SKU separate shipment items retain independent allowance',[v['availableQty'] for v in multi]==['1.999999','1.999998'])
    owner=core['ids']['归属权限'];uid=sql('SELECT owner_user_id FROM ful_order WHERE id=%s',(owner['order'],))[0][0]
    username=sql('SELECT username FROM system_users WHERE id=%s',(uid,))[0][0]
    other=base.Client(48082).login(username[:-5]+'Other');none=base.Client(48082).login(username[:-5]+'None')
    check('allowance enforces owner boundary',allowance(other,owner,False)['code']==1080000003)
    check('allowance requires its query permission',allowance(none,owner,False)['code']==403)
    check('allowance requires authentication',allowance(base.Client(48082),owner,False)['code']==401)
    bad=c.api('GET','/fulfillment/return/allowance',params={'orderId':fx['order'],'shipmentId':cf['shipment']},ok=False)
    check('allowance hides shipment from another order',bad['code']==1080000022)
    foreign=core['ids']['外租户退回'];check('tenant boundary applies to allowance',allowance(c,foreign,False)['code']==1080000003)
    latest=base.Fixture(c,'Latest');new=latest.shipment('最终产物收货',('2.123456',));sid=new['lines'][0]['id']
    check('fresh allowance initially uncommitted',allowance(c,new)[0]['availableQty']=='2.123456')
    request=c.create_return(new['order'],new['shipment'],[(sid,'1.000001')]);before=base.balance(new)
    v=allowance(c,new);check('application changes allowance but not physical',v[0]['committedQty']=='1.000001' and v[0]['availableQty']=='1.123455' and before==(D('17.876544'),D(0)))
    received=c.receive(new['order'],request['id']);check('final artifact receipt uses ERP once',received['status']=='RECEIVED' and base.balance(new)==(D('18.876545'),D(0)))
    check('receipt moves requested to received without double counting allowance',allowance(c,new)==v)
    original=sql('SELECT id FROM ful_return WHERE order_id=%s ORDER BY id LIMIT 1',(fx['order'],))[0][0]
    key,saved=sql("SELECT idempotency_key,response_json FROM ful_command_record WHERE command_type='RETURN_RECEIVE' AND JSON_UNQUOTE(JSON_EXTRACT(response_json,'$.id'))=%s ORDER BY id LIMIT 1",(str(original),))[0]
    check('prior receipt key survives final artifact restart',c.receive(fx['order'],original,key)==json.loads(saved))
    env=os.environ.copy();env.update(API_BASE='http://127.0.0.1:48082',M0_EVIDENCE='M4.2-ERP-regression.json')
    with (ROOT/'.local/m4-return-erp-regression.log').open('wb') as out:r=subprocess.run([sys.executable,str(ROOT/'tests/m0_smoke.py')],env=env,stdout=out,stderr=subprocess.STDOUT,timeout=150)
    check('legacy ERP regression passes on final artifact',r.returncode==0)
    base.invariants()
    E['latest_fixture']=new;E['result']='passed'
except Exception as error:E['result']='failed';E['error']=str(error);raise
finally:
    for proc,out in base.OWNED:base.stop(proc);out.close()
    E['all_owned_processes_stopped']=all(p.poll() is not None for p,_ in base.OWNED)
    (ROOT/'../学习资料/10-验收证据/M4.2-final-api.json').write_text(json.dumps(E,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
    print('M4.2 final API',E.get('result'),len(E['checks']),'checks')
