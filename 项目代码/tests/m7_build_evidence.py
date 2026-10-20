"""Archive only this build's selected JUnit suites and actual reactor log."""
import shutil,xml.etree.ElementTree as ET
from datetime import datetime,timezone
import m7_support as h
names=['OrderStatusCalculatorTest','AllocationPlannerTest','DatabaseCommandRetryTest','LogisticsSignatureTest','FulExpiryScannerTest','ReconcileEngineTest','FulfillmentEventTest','ImportCsvTest']
log=h.ROOT/'.local/m7-final-build.log';body=log.read_text(encoding='utf-8',errors='replace');assert 'BUILD SUCCESS' in body
suites=[]
for name in names:
    matches=list((h.ROOT/'backend/yudao-module-fulfillment/target/surefire-reports').glob('TEST-*.'+name+'.xml'));assert len(matches)==1,name
    p=matches[0];root=ET.parse(p).getroot();assert int(root.get('failures'))==int(root.get('errors'))==int(root.get('skipped'))==0
    dest=h.OUT/('M7-junit-'+name+'.xml');shutil.copyfile(p,dest);suites.append({'name':name,'tests':int(root.get('tests')),'evidence':dest.name,'sha256':h.sha(dest)})
assert sum(x['tests'] for x in suites)==60
shutil.copyfile(log,h.OUT/'M7-backend-build.log')
h.save('M7-build.json',{'run_at':datetime.now(timezone.utc).isoformat(),'backend_sha256':h.sha(h.JAR),'selected_tests':60,'modules':22,'suites':suites,'result':'passed','scope':'Selected eight fulfillment suites; not all upstream tests.'})
