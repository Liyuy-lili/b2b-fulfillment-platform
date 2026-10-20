"""Replay existing business assertions without overwriting historical evidence.
Adapters only change isolation/fixture grants/current migration expectations.
Original source hashes and controlled string substitutions are recorded.
"""
import ast,hashlib,importlib.util,json,os,shutil,subprocess,sys,time,uuid
from datetime import datetime,timezone
from pathlib import Path
import m7_support as h
CASE=sys.argv[1];STAMP=datetime.now().strftime('%Y%m%d_%H%M%S');DB='fulfillment_m7_reg_'+CASE+'_'+STAMP
if CASE=='file':DB=h.load('M7.2-filefoundation.json')['database']
os.environ.update(DB_NAME=DB,M4_DATABASE=DB,M4_RETURN_DATABASE=DB,M6_DATABASE=DB,API_BASE='http://127.0.0.1:48082',M1_EVIDENCE='M7.2-expiry-binding.json',M2_SECONDARY_LOG='m7-core-b-out.log',M2_BASE_EVIDENCE='M7.2-core-m2.json')
META={'run_at':datetime.now(timezone.utc).isoformat(),'case':CASE,'database':DB,'artifact_sha256':h.sha(h.JAR),'sources':[],'adaptations':['Separate M7 schema/Redis DB12/ports; historical evidence files are never replaced.'],'results':[]}
MODULES=[];RUNTIME=h.Runtime(DB,12);POPEN=subprocess.Popen
def controlled_load(name):
    path=h.ROOT/'tests'/(name+'.py');source=path.read_text(encoding='utf-8');changes={
      'M2-acceptance.json':'M7.2-core-m2.json','M6.1-foundation.json':'M7.2-filefoundation.json','M4.1-clean-binding.json':'M7.2-expiry-binding.json','M4.2-clean-binding.json':'M7.2-returns-binding.json',
      '.local/backend-out.log':'.local/m7-core-a-out.log','.local/m3-fault-out.log':'.local/m7-core-fault-out.log'}
    class Replacements(ast.NodeTransformer):
        def visit_Constant(self,node):
            if isinstance(node.value,str):
                for old,new in changes.items():node.value=node.value.replace(old,new)
            return node
    tree=ast.fix_missing_locations(Replacements().visit(ast.parse(source,filename=str(path))))
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);sys.modules[name]=module;exec(compile(tree,str(path),'exec'),module.__dict__)
    META['sources'].append({'path':str(path.relative_to(h.ROOT)),'sha256':h.sha(path),'string_substitutions':changes});MODULES.append(module);return module
def intercept_popen(args,*a,**kw):
    values=list(args) if not isinstance(args,str) else args
    if isinstance(values,list) and str(values[0]).lower().endswith(('java.exe','java')) and '-jar' in values:
        values=[v for v in values if not str(v).startswith('--spring.data.redis.database=')]+['--spring.data.redis.database=12']
        env=dict(kw.get('env') or os.environ);env['DB_NAME']=DB;assert int(env.get('APP_PORT',48080))!=48080 or any(str(x).startswith('--server.port=') and x!='--server.port=48080' for x in values)
        kw['env']=env
    return POPEN(values,*a,**kw)
def prepare(module):
    os.environ['DB_NAME']=DB
    if hasattr(module,'DATABASE'):module.DATABASE=DB
    if hasattr(module,'VHOST'):module.VHOST=DB
    if hasattr(module,'E'):module.E.update(database=DB,redis_database=12,run_at=datetime.now(timezone.utc).isoformat())
    original=module.check
    def check(name,ok,detail=None):
        if 'history' in name and ('through' in name or '0 through' in name):
            expected=tuple(str(v) for v in range(9));actual=tuple(r[0] for r in h.sql(DB,'SELECT version FROM ful_flyway_schema_history ORDER BY installed_rank'));ok=actual==expected;detail={'current':actual,'expected':expected};name+=' [M7 expected V0-V8]'
        return original(name,ok,detail)
    module.check=check;return module
def record(module,label):
    value=module.E;value.update(artifact_sha256=META['artifact_sha256'],m7_case=CASE,redis_database=12,actual_application_ports=[48082,48083,48084] if CASE=='core' else [48082,48083]);assert value.get('result')=='passed' and all(x['passed'] for x in value['checks'])
    h.save('M7.2-'+label+'.json',value);META['results'].append({'evidence':'M7.2-'+label+'.json','checks':len(value['checks'])})
def core():
    META['commands']=h.initialize(DB)
    import m1_acceptance as one
    import m2_acceptance as two
    init=two.M2Client.__init__
    def mapped(self,port=48080,tenant=1):init(self,{48080:48082,48082:48083,48083:48084}.get(port,port),tenant)
    two.M2Client.__init__=mapped
    # M3's current contract explicitly expects M4's natural expiry scanner.
    RUNTIME.start(48082,'core-a',{'fulfillment.expiry.enabled':'true'});RUNTIME.start(48083,'core-b',{'fulfillment.expiry.enabled':'true'});fault=RUNTIME.start(48084,'core-fault',{'spring.profiles.active':'fulfillment,fulfillment-fault-test'})
    one.main();record(one,'core-binding')
    two.main();record(two,'core-m2')
    legacy=prepare(controlled_load('m2_legacy_inventory'));legacy.main();record(legacy,'core-legacy')
    three=prepare(controlled_load('m3_acceptance'));callback=three.callback
    def route_callback(*a,**kw):kw['port']={48080:48082,48082:48083,48083:48084}.get(kw.get('port',48080),kw.get('port',48080));return callback(*a,**kw)
    three.callback=route_callback;three.main();record(three,'core-m3')
    shutil.copyfile(h.ROOT/'.local/m7-core-fault-out.log',h.OUT/'M7.2-core-after-erp-fault.log');RUNTIME.stop(fault)
    # Positive fixture users now need explicit OPERATE in addition to their
    # historical function/owner permissions. Do not grant to negative users.
    login=three.M3Client.login
    def alice_login(self,name='admin'):
        result=login(self,name)
        if name.endswith('Alice'):
            admin=three.M3Client().login();uid=h.sql(DB,'SELECT id FROM system_users WHERE username=%s AND tenant_id=1',(name,))[0][0];wh=two.E['ids']['warehouse_a'];admin.api('POST','/fulfillment/warehouse/grant',{'userId':str(uid),'warehouseId':str(wh),'permission':'OPERATE','enabled':True,'reason':'M7 historical positive fixture requires M6 warehouse scope'},headers={'Idempotency-Key':uuid.uuid4().hex});META['adaptations'].append({'positive_fixture_warehouse_grant':{'user':uid,'warehouse':wh}})
        return result
    three.M3Client.login=alice_login
    perms=prepare(controlled_load('m3_permissions'));perms.main();record(perms,'core-m3-permissions')
    RUNTIME.start(48084,'core-fault',{'spring.profiles.active':'fulfillment,fulfillment-fault-test','fulfillment.test.fail-during-erp':'true'})
    erp=prepare(controlled_load('m3_erp_failure'));erp.main();record(erp,'core-erp-fault')
    # The complete old ERP smoke stays in this schema and this JVM.
    env=os.environ.copy();env['M0_EVIDENCE']='M7.2-core-ERP.json'
    log=h.ROOT/'.local/m7-core-erp-smoke.log'
    with log.open('wb') as out:r=subprocess.run([sys.executable,str(h.ROOT/'tests/m0_smoke.py')],env=env,stdout=out,stderr=subprocess.STDOUT,timeout=240)
    assert r.returncode==0;META['results'].append({'evidence':'M7.2-core-ERP.json','checks':len(h.load('M7.2-core-ERP.json')['checks'])})
def suite():
    name={'expiry':'m4_expiry_acceptance','returns':'m4_return_acceptance','reconcile':'m4_reconcile_acceptance','message':'m5_acceptance','filefoundation':'m6_foundation','file':'m6_acceptance'}[CASE]
    module=prepare(controlled_load(name))
    if CASE in ['returns','message']:
        login=module.Client.login
        def owner_login(self,name='admin'):
            result=login(self,name)
            if name==module.RUN+'Owner':
                admin=module.Client(48082).login();uid=h.sql(DB,'SELECT id FROM system_users WHERE tenant_id=1 AND username=%s',(name,))[0][0];wh=h.sql(DB,'SELECT id FROM erp_warehouse WHERE tenant_id=1 AND deleted=0 ORDER BY id LIMIT 1')[0][0]
                admin.api('POST','/fulfillment/warehouse/grant',{'userId':str(uid),'warehouseId':str(wh),'permission':'OPERATE','enabled':True,'reason':'M7 positive operator fixture scope'},headers={'Idempotency-Key':uuid.uuid4().hex});META['adaptations'].append({'positive_fixture_scope':{'user':uid,'warehouse':wh}})
            return result
        module.Client.login=owner_login
    if CASE=='message':
        shell=module.shell;start=module.start
        def safe_shell(file,*args):
            if str(file).endswith(('Stop-Messaging.ps1','Start-Messaging.ps1')):
                assert h.free(35676);META['adaptations'].append({'transport_outage':'Test application connects to closed port35676; shared Broker stays running.'});return
            return shell(file,*args)
        def outage_start(label,port=48083,publisher=False,consumer=False,test=()):
            if label=='enabled-while-broker-down':test=tuple(test)+('--fulfillment.messages.port=35676',)
            return start(label,port,publisher,consumer,test)
        module.shell=safe_shell;module.start=outage_start
    module.main()
    if CASE=='message':
        # The historical "offline" check runs with workers disabled. Add an
        # actual unreachable-transport boot with both workers enabled, then
        # recover only this application's connection, keeping shared MQ alive.
        for proc,out in module.OWNED:module.stop(proc)
        offline=module.start('enabled-while-broker-down',48082,True,True,('--fulfillment.messages.max-attempts=10','--fulfillment.expiry.enabled=false'))
        client=module.Client(48082).login();fixture=module.b.Fixture(client,'M7UnreachableTransport');fx=fixture.shipment('真正传输不可达',('1',))
        module.wait(lambda:bool(h.sql(DB,"SELECT id FROM ful_outbox_event WHERE order_id=%s AND last_error IS NOT NULL AND attempts>0",(fx['order'],))))
        module.check('M7 enabled workers boot and shipping commit while transport connection refused',h.sql(DB,'SELECT COUNT(*) FROM ful_outbox_event WHERE order_id=%s',(fx['order'],))[0][0]==3)
        facts=module.facts();module.stop(offline)
        recovered=module.start('enabled-transport-recovery',48082,True,True,('--fulfillment.messages.max-attempts=10','--fulfillment.expiry.enabled=false'))
        module.wait(lambda:h.sql(DB,"SELECT COUNT(*) FROM ful_outbox_event o LEFT JOIN ful_inbox_event i ON i.tenant_id=o.tenant_id AND i.event_id=o.event_id WHERE o.order_id=%s AND (o.status<>'SENT' OR i.id IS NULL OR i.status<>'PROCESSED')",(fx['order'],))[0][0]==0,150)
        module.check('M7 restoring application connection drains persisted events with exact business facts',module.facts()==facts)
        module.E['unreachable_transport_fixture']=fx;module.stop(recovered)
    record(module,CASE)
try:
    subprocess.Popen=intercept_popen
    if CASE=='core':core()
    else:suite()
    META['result']='passed'
except Exception as error:
    META.update(result='failed',error=str(error))
    for module in MODULES:
        if hasattr(module,'E'):h.save('M7.2-'+CASE+'-partial-'+STAMP+'-'+module.__name__+'.json',module.E)
    raise
finally:
    stopped=RUNTIME.close()
    seen=set()
    for module in MODULES:
        for collection in [getattr(module,'OWNED',[]),getattr(module,'PROCESSES',[])]:
            for entry in collection:
                if not isinstance(entry,tuple):continue
                p,out=entry[:2]
                if p.pid in seen:continue
                seen.add(p.pid)
                if p.poll() is None:
                    p.terminate()
                    try:p.wait(25)
                    except subprocess.TimeoutExpired:p.kill();p.wait(10)
                out.close();stopped=stopped and p.poll() is not None
        if hasattr(module,'POOL'):module.POOL.shutdown(wait=True)
    # file core owns processes in its imported m6_foundation helper.
    if 'm6_foundation' in sys.modules:
        for p,out in sys.modules['m6_foundation'].OWNED:
            if p.poll() is None:p.terminate();p.wait(25)
            out.close();stopped=stopped and p.poll() is not None
    META['all_owned_stopped']=stopped
    if CASE=='filefoundation' and META.get('result')=='passed':
        MODULES[-1].E['all_owned_processes_stopped']=stopped;h.save('M7.2-filefoundation.json',MODULES[-1].E)
    subprocess.Popen=POPEN
    for pattern in ['m7-core-*.log',{'expiry':'m4-expiry-*-out.log','returns':'m4-return-*-out.log','reconcile':'m4-reconcile-*-out.log','message':'m5-*-out.log','filefoundation':'m6-foundation-*-out.log','file':'m6-core-*-out.log'}.get(CASE,'m7-nomatch')]:
        for path in (h.ROOT/'.local').glob(pattern):shutil.copyfile(path,h.OUT/('M7.2-'+CASE+'-'+STAMP+'-'+path.name))
    if META.get('result')=='failed':h.save('M7.2-'+CASE+'-failed-'+STAMP+'.json',META)
    h.save('M7.2-'+CASE+'-run.json',META);print('M7 regression',CASE,META.get('result'),flush=True)
