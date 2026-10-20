'use strict';
// Node built-ins only. Real HTTP fixtures; no business SQL and no fixture deletion.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const config = JSON.parse(fs.readFileSync(process.argv[2],'utf8').replace(/^\uFEFF/,''));
const root = path.resolve(__dirname,'..');
const data = path.join(root,'data'); fs.mkdirSync(data,{recursive:true});
const statePath = path.join(data,'demo.json');
const state = fs.existsSync(statePath) ? JSON.parse(fs.readFileSync(statePath,'utf8')) : {formatVersion:1,source:'M7DEMO_'+Date.now(),ids:{},keys:{},complete:false};
const base = 'http://127.0.0.1:'+config.frontendPort+'/admin-api';
let token;
function save(){fs.writeFileSync(statePath,JSON.stringify(state,null,2)+'\n');}
async function api(method,route,body,key,anonymous=false){
  const headers={'tenant-id':'1'};if(!anonymous)headers.Authorization='Bearer '+token;
  if(body!==undefined)headers['Content-Type']='application/json';if(key)headers['Idempotency-Key']=key;
  const response=await fetch(base+route,{method,headers,body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(60000)});
  const result=await response.json();assert.equal(response.status,200,route);assert.equal(result.code,0,route+': '+JSON.stringify(result));return result.data;
}
async function remembered(name,work){if(state.ids[name]!==undefined)return state.ids[name];const result=await work();state.ids[name]=result;save();return result;}
function key(name){if(!state.keys[name]){state.keys[name]='M7.demo:'+state.source+':'+name;save();}return state.keys[name];}
async function create(name,kind,body){return remembered(name,()=>api('POST','/erp/'+kind+'/create',body));}
async function approve(kind,id){return api('PUT','/erp/'+kind+'/update-status?id='+id+'&status=20');}
async function waitJob(id){for(let n=0;n<240;n++){const j=await api('GET','/fulfillment/job/get?id='+id);if(['SUCCEEDED','PARTIAL_FAILED','FAILED','CANCELLED'].includes(j.status))return j;await new Promise(r=>setTimeout(r,500));}throw Error('Job timeout '+id);}
async function download(id,kind,name){const response=await fetch(base+'/fulfillment/job/download?id='+id+'&kind='+kind,{headers:{'tenant-id':'1',Authorization:'Bearer '+token},signal:AbortSignal.timeout(60000)});const bytes=Buffer.from(await response.arrayBuffer());assert.equal(response.status,200);assert.ok(!response.headers.get('content-type').includes('json'));fs.writeFileSync(path.join(data,name),bytes);return bytes.length;}
async function main(){
  const login=await api('POST','/system/auth/login',{username:'admin',password:'admin123'},null,true);token=login.accessToken;
  if(state.complete){const o=await api('GET','/fulfillment/order/get?id='+state.ids.bound.orderId);assert.equal(o.id,state.ids.bound.orderId);console.log('M7_DEMO_REUSED '+statePath);return;}
  save();const now=new Date().toISOString().slice(0,19);
  const unit=await create('unit','product-unit',{name:'演示件',status:0});
  const category=await create('category','product-category',{name:'演示商品分类',code:state.source,parentId:0,sort:1,status:0});
  const customer=await create('customer','customer',{name:'演示采购客户',sort:1,status:0});
  const supplier=await create('supplier','supplier',{name:'演示供应商',sort:1,status:0});
  const account=await create('account','account',{name:'演示结算账户',no:state.source,sort:1,status:0});
  const a=await create('warehouseA','warehouse',{name:'演示西安仓',sort:1,status:0,warehousePrice:'0',truckagePrice:'0'});
  const b=await create('warehouseB','warehouse',{name:'演示上海仓',sort:2,status:0,warehousePrice:'0',truckagePrice:'0'});
  const product=await create('product','product',{name:'演示工业连接器',barCode:state.source,categoryId:category,unitId:unit,status:0,purchasePrice:'0',salePrice:'2.345678'});
  for(const [name,w,count] of [['inA',a,'6'],['inB',b,'8']]){
    const id=await create(name,'stock-in',{supplierId:supplier,inTime:now,items:[{productId:product,warehouseId:w,count,productPrice:'0'}]});
    await remembered(name+'Approved',async()=>{await approve('stock-in',id);return true;});
  }
  const source=await create('sourceOrder','sale-order',{customerId:customer,accountId:account,orderTime:now,discountPercent:'0',items:[{productId:product,count:'10',productPrice:'2.345678',taxPercent:'0'}]});
  await remembered('sourceApproved',async()=>{await approve('sale-order',source);return true;});
  const bound=await remembered('bound',()=>api('POST','/fulfillment/order/bind',{erpOrderId:String(source)},key('bind')));
  const allocation=await remembered('allocation',()=>api('POST','/fulfillment/order/allocate',{orderId:bound.orderId,warehouseIds:[String(b),String(a)],strategy:'PRIORITY_SPLIT',holdSeconds:900},key('allocate')));
  assert.equal(allocation.outcome,'ALLOCATED');const reservation=allocation.reservations.find(r=>r.warehouseId===String(a));assert.ok(reservation);
  const shipped=await remembered('shipped',()=>api('POST','/fulfillment/shipment/confirm',{orderId:bound.orderId,warehouseId:String(a),items:[{id:reservation.id,quantity:'4'}],carrierCode:'SIMULATED',trackingNo:state.source},key('ship')));
  const order=await api('GET','/fulfillment/order/get?id='+bound.orderId);
  await remembered('cancelled',()=>api('POST','/fulfillment/order/cancel',{orderId:bound.orderId,items:[{id:order.items[0].id,quantity:'6'}],reason:'演示客户取消剩余6件'},key('cancel')));
  await remembered('delivered',()=>api('POST','/fulfillment/logistics/simulate',{shipmentId:shipped.shipmentId,eventType:'DELIVERED'}));
  const shipment=await api('GET','/fulfillment/shipment/get?id='+shipped.shipmentId);
  const returned=await remembered('returned',()=>api('POST','/fulfillment/return/create',{orderId:bound.orderId,shipmentId:shipped.shipmentId,items:[{id:shipment.items[0].id,quantity:'2'}],reason:'演示实际退回2件'},key('return')));
  await remembered('received',()=>api('POST','/fulfillment/return/receive',{orderId:bound.orderId,returnId:returned.id},key('receive')));
  const csv='\uFEFFexternalOrderNo,customerCode,productCode,quantity,unitPrice\r\n'+state.source+'-A,'+customer+','+state.source+',1.000001,2.345678\r\n'+state.source+'-Bad,'+customer+','+state.source+',0,2\r\n';
  fs.writeFileSync(path.join(data,'demo-import.csv'),csv);
  const uploaded=await remembered('upload',async()=>{const form=new FormData();form.append('file',new Blob([csv],{type:'text/csv'}),'demo-import.csv');const response=await fetch(base+'/fulfillment/job/upload',{method:'POST',headers:{'tenant-id':'1',Authorization:'Bearer '+token},body:form});const result=await response.json();assert.equal(result.code,0);return result.data;});
  for(const name of ['import','duplicateImport']){
    const job=await remembered(name,()=>api('POST','/fulfillment/job/import',{fileId:uploaded.fileId,sourceSystem:state.source},key(name)));const result=await waitJob(job.jobId);assert.equal(result.status,'PARTIAL_FAILED');assert.equal(result.successRows,1);assert.equal(result.failedRows,1);
  }
  const exported=await remembered('export',()=>api('POST','/fulfillment/job/export',{dataset:'STOCK',warehouseIds:[String(a),String(b)]},key('export')));
  assert.equal((await waitJob(exported.jobId)).status,'SUCCEEDED');
  state.downloads={errorBytes:await download(state.ids.duplicateImport.jobId,'ERROR','demo-error.csv'),xlsxBytes:await download(exported.jobId,'RESULT','demo-stock.xlsx')};save();
  const role=await remembered('warehouseRole',()=>api('POST','/system/role/create',{name:'演示仓库只读角色',code:'M7_WAREHOUSE',sort:1,status:0}));
  await remembered('warehouseMenu',async()=>{await api('POST','/system/permission/assign-role-menu',{roleId:role,menuIds:[597,50019,50021,50024]});return true;});
  const user=await remembered('warehouseUser',()=>api('POST','/system/user/create',{username:'m7warehouse',nickname:'演示仓库人员',password:'admin123'}));
  await remembered('warehouseRoleAssigned',async()=>{await api('POST','/system/permission/assign-user-role',{userId:user,roleIds:[role]});return true;});
  await remembered('warehouseGrant',()=>api('POST','/fulfillment/warehouse/grant',{userId:String(user),warehouseId:String(a),permission:'READ',enabled:true,reason:'演示账号只能查看西安仓'},key('grant')));
  for(let n=0;n<180;n++){const projection=await api('GET','/fulfillment/message/projection?orderId='+bound.orderId);if(projection && projection.observedVersion===projection.businessVersion){state.projection=projection;break;}await new Promise(r=>setTimeout(r,500));}
  assert.ok(state.projection,'Execution read model did not reach current business version');
  const report=await remembered('reconciliation',()=>api('POST','/fulfillment/reconcile/run',{scope:'TENANT'},key('scan')));assert.equal(report.differenceCount,0);
  state.complete=true;state.completedAt=new Date().toISOString();save();console.log('M7_DEMO_READY '+statePath);
}
main().catch(e=>{console.error(e.stack);process.exitCode=1;});
