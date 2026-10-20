package cn.iocoder.yudao.module.fulfillment.domain;

import java.math.BigDecimal;
import java.util.*;
import java.util.function.Predicate;
import static java.math.BigDecimal.ZERO;

/** Pure rules over one bounded tenant snapshot. No I/O, locks or repair writes. */
public final class ReconcileEngine {
    public static final String VERSION="M4.3-v1";
    public record Row(Map<String,Object> values) {
        public long id(){return n("id");}
        public long n(String k){Object v=values.get(k);return v==null?0:((Number)v).longValue();}
        public BigDecimal q(String k){Object v=values.get(k);return v==null?ZERO:new BigDecimal(v.toString());}
        public String s(String k){return Objects.toString(values.get(k),"");}
        public boolean flag(String k){Object v=values.get(k);return Boolean.TRUE.equals(v)||(v instanceof Number n&&n.intValue()!=0);}
        public boolean live(){return !flag("deleted");}
    }
    public record Finding(String ruleCode,String objectType,long objectId,Long orderId,Long productId,Long warehouseId,String expectedValue,String actualValue,String detail) {}
    private record Key(long product,long warehouse) {}
    private final Map<String,List<Row>> data;
    private final Map<String,Map<Long,Row>> indices=new HashMap<>();
    private final List<Finding> differences=new ArrayList<>();
    private final int maxDifferences;
    public ReconcileEngine(Map<String,List<Row>> data,int maxDifferences){this.data=data;this.maxDifferences=maxDifferences;}
    private List<Row> rows(String t){return data.getOrDefault(t,List.of());}
    private Row get(String t,long id){return indices.computeIfAbsent(t,k->{Map<Long,Row> m=new HashMap<>();for(Row r:rows(k))m.put(r.id(),r);return m;}).get(id);}
    private boolean same(Row r,String field,long value){return r!=null&&r.live()&&r.n(field)==value;}
    private BigDecimal sum(String table,String quantity,Predicate<Row> predicate){return rows(table).stream().filter(predicate).map(r->r.q(quantity)).reduce(ZERO,BigDecimal::add);}
    private void add(String code,String table,Row r,Object expected,Object actual,String detail){
        if(differences.size()>=maxDifferences)throw new LimitExceeded();
        differences.add(new Finding(code,table,r.id(),r.n("order_id")==0?null:r.n("order_id"),r.n("product_id")==0?null:r.n("product_id"),r.n("warehouse_id")==0?null:r.n("warehouse_id"),text(expected),text(actual),detail));
    }
    private static String text(Object x){return x instanceof BigDecimal n?n.toPlainString():String.valueOf(x);}
    private void equal(String code,String table,Row r,BigDecimal expected,BigDecimal actual,String detail){if(expected.compareTo(actual)!=0)add(code,table,r,expected,actual,detail);}
    private void relation(String code,String table,Row r,boolean ok,String detail){if(!ok)add(code,table,r,"valid","missing/deleted/mismatched",detail);}
    public static final class LimitExceeded extends RuntimeException {}
    public List<Finding> check(){stocks();orders();reservations();shipments();returns();return List.copyOf(differences);}

    private void stocks(){
        Map<Key,Row> stocks=new LinkedHashMap<>();Set<Key> keys=new LinkedHashSet<>();
        for(String table:List.of("erp_stock","erp_stock_record","ful_reservation","ful_stock_ledger"))for(Row r:rows(table)){
            Key key=new Key(r.n("product_id"),r.n("warehouse_id"));keys.add(key);if(table.equals("erp_stock"))stocks.put(key,r);
        }
        for(Key k:keys){
            Row s=stocks.get(k);Predicate<Row> p=r->r.n("product_id")==k.product&&r.n("warehouse_id")==k.warehouse;
            if(s==null){add("STOCK_MISSING","stock_key",new Row(Map.of("id",0L,"product_id",k.product,"warehouse_id",k.warehouse)),"stock row","absent","流水或预占存在，但库存汇总行缺失");continue;}
            relation("STOCK_DELETED","erp_stock",s,s.live(),"库存汇总不能逻辑删除");
            equal("STOCK_H_LEDGER","erp_stock",s,sum("erp_stock_record","count",p),s.q("count"),"H应等于ERP全部正负实物流水之和，含撤销流水");
            equal("STOCK_R_HELD","erp_stock",s,sum("ful_reservation","held_qty",p),s.q("ful_reserved_count"),"R应等于本商品本仓所有held之和");
            equal("STOCK_R_LEDGER","erp_stock",s,sum("ful_stock_ledger","held_delta",p),s.q("ful_reserved_count"),"预占流水仅核对R，不叠加ERP的H流水");
            relation("STOCK_RANGE","erp_stock",s,s.q("ful_reserved_count").signum()>=0&&s.q("count").compareTo(s.q("ful_reserved_count"))>=0,"必须H>=R>=0");
        }
        for(String table:List.of("erp_stock_record","ful_stock_ledger")){
            Map<Key,BigDecimal> running=new HashMap<>();
            for(Row l:rows(table)){
                Key k=new Key(l.n("product_id"),l.n("warehouse_id"));boolean physical=table.equals("erp_stock_record");
                BigDecimal after=running.getOrDefault(k,ZERO).add(l.q(physical?"count":"held_delta"));running.put(k,after);
                equal(physical?"STOCK_H_RUNNING":"STOCK_R_RUNNING",table,l,after,l.q(physical?"total_count":"reserved_after"),"按同商品同仓流水ID顺序重新计算逐笔余额");
            }
        }
    }
    private void orders(){
        for(Row i:rows("ful_order_item")){
            long id=i.id();Row o=get("ful_order",i.n("order_id"));Row source=get("erp_sale_order_items",i.n("erp_order_item_id"));
            relation("ORDER_ITEM_SOURCE","ful_order_item",i,o!=null&&o.live()&&source!=null&&source.live()&&source.n("order_id")==o.n("erp_order_id")&&source.n("product_id")==i.n("product_id")&&source.n("product_unit_id")==i.n("unit_id")&&source.q("count").compareTo(i.q("ordered_qty"))==0&&source.q("product_price").compareTo(i.q("price_snapshot"))==0,"履约项应关联同源单的商品、单位、数量和冻结单价");
            equal("ORDER_RESERVED","ful_order_item",i,sum("ful_reservation","held_qty",r->r.n("order_item_id")==id),i.q("reserved_qty"),"订单预占汇总=held");
            equal("ORDER_SHIPPED","ful_order_item",i,sum("ful_shipment_item","quantity",r->r.n("order_item_id")==id),i.q("shipped_qty"),"累计发货=发货项之和，不扣退货");
            equal("ORDER_CANCELLED","ful_order_item",i,sum("ful_cancellation","quantity",r->r.n("order_item_id")==id),i.q("cancelled_qty"),"取消汇总=取消事实之和");
            equal("ORDER_RETURNED","ful_order_item",i,sum("ful_return_item","quantity",r->r.n("order_item_id")==id&&received(r)),i.q("returned_qty"),"退货汇总仅计算RECEIVED");
            if(source!=null){equal("SOURCE_OUT_COUNT","ful_order_item",i,i.q("shipped_qty"),source.q("out_count"),"托管源项outCount=履约gross shipped");equal("SOURCE_RETURN_COUNT","ful_order_item",i,i.q("returned_qty"),source.q("return_count"),"托管源项returnCount=已收退货");}
        }
        for(Row o:rows("ful_order")){
            Row source=get("erp_sale_order",o.n("erp_order_id"));
            relation("ORDER_SOURCE","ful_order",o,source!=null&&source.live()&&source.n("status")==20&&source.s("no").equals(o.s("order_no")),"源销售单应存在、已审核且单号匹配");
            List<Row> lines=rows("ful_order_item").stream().filter(i->i.n("order_id")==o.id()).toList();
            try{
                var q=lines.stream().map(i->new OrderQuantities(i.q("ordered_qty"),i.q("open_qty"),i.q("reserved_qty"),i.q("shipped_qty"),i.q("cancelled_qty"),i.q("returned_qty"))).toList();
                String expected=OrderStatusCalculator.calculate(q,o.flag("allocation_attempted")).name();
                if(!expected.equals(o.s("status")))add("ORDER_STATUS","ful_order",o,expected,o.s("status"),"按逐项数量重新计算状态");
            }catch(IllegalArgumentException e){add("ORDER_QUANTITY","ful_order",o,"valid per-item invariant","invalid","订购=open+reserved+shipped+cancelled且0<=returned<=shipped");}
            if(source!=null){
                equal("SOURCE_HEADER_OUT","ful_order",o,lines.stream().map(i->i.q("shipped_qty")).reduce(ZERO,BigDecimal::add),source.q("out_count"),"核对基座源单outCount投影，不作为跨商品可用量");
                equal("SOURCE_HEADER_RETURN","ful_order",o,lines.stream().map(i->i.q("returned_qty")).reduce(ZERO,BigDecimal::add),source.q("return_count"),"核对基座源单returnCount投影");
                Set<Long> mapped=new HashSet<>();for(Row i:lines)mapped.add(i.n("erp_order_item_id"));
                for(Row si:rows("erp_sale_order_items"))if(si.live()&&si.n("order_id")==source.id()&&!mapped.contains(si.id()))add("SOURCE_ITEM_UNMAPPED","erp_sale_order_items",si,"fulfillment item","absent","托管源单存在未映射商品项");
            }
        }
        for(String table:List.of("ful_order","ful_order_item","ful_reservation","ful_stock_ledger","ful_shipment","ful_shipment_item","ful_cancellation","ful_return","ful_return_item"))for(Row r:rows(table))relation("FACT_DELETED",table,r,r.live(),"履约核对包含历史事实，逻辑删除需人工检查");
        for(Row c:rows("ful_cancellation"))relation("CANCELLATION_ORIGIN","ful_cancellation",c,same(get("ful_order_item",c.n("order_item_id")),"order_id",c.n("order_id")),"取消事实必须属于原订单项");
    }
    private void reservations(){
        for(Row r:rows("ful_reservation")){
            Row i=get("ful_order_item",r.n("order_item_id"));
            relation("RESERVATION_ORIGIN","ful_reservation",r,same(i,"order_id",r.n("order_id"))&&i.n("product_id")==r.n("product_id"),"预占商品/订单应匹配订单项");
            equal("RESERVATION_BALANCE","ful_reservation",r,r.q("allocated_qty"),r.q("held_qty").add(r.q("consumed_qty")).add(r.q("released_qty")),"allocated=held+consumed+released");
            equal("RESERVATION_LEDGER","ful_reservation",r,r.q("held_qty"),sum("ful_stock_ledger","held_delta",l->l.n("reservation_id")==r.id()),"该预占的全部增减流水应归结为held");
            equal("RESERVATION_SHIPPED","ful_reservation",r,r.q("consumed_qty"),sum("ful_shipment_item","quantity",s->s.n("reservation_id")==r.id()),"consumed应由实际发货项解释");
            relation("RESERVATION_ACTIVE","ful_reservation",r,r.flag("active_flag")== (r.q("held_qty").signum()>0),"activeFlag与held>0一致；截止时间本身不等于已释放");
        }
        for(Row l:rows("ful_stock_ledger")){
            Row r=get("ful_reservation",l.n("reservation_id"));
            relation("RESERVATION_LEDGER_ORIGIN","ful_stock_ledger",l,r!=null&&r.live()&&r.n("product_id")==l.n("product_id")&&r.n("warehouse_id")==l.n("warehouse_id"),"预占流水必须映射同商品同仓预占");
        }
    }
    private void shipments(){
        for(Row s:rows("ful_shipment")){
            Row order=get("ful_order",s.n("order_id"));Row e=get("erp_sale_out",s.n("erp_sale_out_id"));
            relation("SHIPMENT_ERP_HEAD","ful_shipment",s,order!=null&&e!=null&&e.live()&&e.n("status")==20&&e.n("order_id")==order.n("erp_order_id"),"原发货应关联同销售单已审核ERP出库");
            relation("SHIPMENT_ITEMS","ful_shipment",s,rows("ful_shipment_item").stream().anyMatch(i->i.n("shipment_id")==s.id()),"发货主单必须有明细");
        }
        for(Row i:rows("ful_shipment_item")){
            Row s=get("ful_shipment",i.n("shipment_id")),o=get("ful_order_item",i.n("order_item_id")),r=get("ful_reservation",i.n("reservation_id")),e=get("erp_sale_out_items",i.n("erp_sale_out_item_id"));
            relation("SHIPMENT_ORIGIN","ful_shipment_item",i,s!=null&&o!=null&&r!=null&&s.n("order_id")==i.n("order_id")&&o.n("order_id")==i.n("order_id")&&r.n("order_item_id")==o.id()&&r.n("warehouse_id")==s.n("warehouse_id"),"发货应关联同订单同仓的订单项和预占");
            boolean valid=s!=null&&o!=null&&e!=null&&e.live()&&e.n("out_id")==s.n("erp_sale_out_id")&&e.n("order_item_id")==o.n("erp_order_item_id")&&e.n("product_id")==o.n("product_id")&&e.n("warehouse_id")==s.n("warehouse_id")&&e.n("product_unit_id")==o.n("unit_id")&&e.q("count").compareTo(i.q("quantity"))==0;
            relation("SHIPMENT_ERP_ITEM","ful_shipment_item",i,valid,"ERP出库项的源项、商品、单位、原仓与数量应匹配");
            List<Row> records=rows("erp_stock_record").stream().filter(l->l.n("biz_type")==50&&s!=null&&l.n("biz_id")==s.n("erp_sale_out_id")&&l.n("biz_item_id")==i.n("erp_sale_out_item_id")).toList();
            relation("SHIPMENT_PHYSICAL","ful_shipment_item",i,records.size()==1&&o!=null&&s!=null&&records.get(0).q("count").compareTo(i.q("quantity").negate())==0&&records.get(0).n("product_id")==o.n("product_id")&&records.get(0).n("warehouse_id")==s.n("warehouse_id"),"托管发货只应有一笔对应ERP实物扣减流水");
            BigDecimal committed=sum("ful_return_item","quantity",ri->ri.n("shipment_item_id")==i.id()&&committed(ri));
            if(committed.compareTo(i.q("quantity"))>0)add("RETURN_ALLOWANCE","ful_shipment_item",i,i.q("quantity"),committed,"申请中+已收货不能超原发货项");
        }
        // Reverse checks catch an extra approved ERP document/item not mapped by fulfillment.
        for(Row e:rows("erp_sale_out"))if(e.live()&&e.n("status")==20&&managedSource(e.n("order_id"))){
            List<Row> mapped=rows("ful_shipment").stream().filter(s->s.n("erp_sale_out_id")==e.id()).toList();
            relation("ERP_OUT_UNMAPPED","erp_sale_out",e,mapped.size()==1,"托管源单的每个已审核ERP出库必须唯一映射履约发货");
            for(Row i:rows("erp_sale_out_items"))if(i.live()&&i.n("out_id")==e.id())relation("ERP_OUT_ITEM_UNMAPPED","erp_sale_out_items",i,rows("ful_shipment_item").stream().filter(s->s.n("erp_sale_out_item_id")==i.id()).count()==1,"已审核托管ERP出库明细必须唯一映射");
        }
    }
    private boolean managedSource(long id){return rows("ful_order").stream().anyMatch(o->o.n("erp_order_id")==id);}
    private boolean received(Row i){Row r=get("ful_return",i.n("return_id"));return r!=null&&r.s("status").equals("RECEIVED");}
    private boolean committed(Row i){Row r=get("ful_return",i.n("return_id"));return r!=null&&Set.of("REQUESTED","RECEIVED").contains(r.s("status"));}
    private void returns(){
        for(Row r:rows("ful_return")){
            Row s=get("ful_shipment",r.n("shipment_id")),o=get("ful_order",r.n("order_id")),e=get("erp_sale_return",r.n("erp_sale_return_id"));
            relation("RETURN_ORIGIN","ful_return",r,s!=null&&s.live()&&s.n("order_id")==r.n("order_id")&&s.n("warehouse_id")==r.n("warehouse_id"),"退货主单必须关联原订单、原发货仓");
            relation("RETURN_ITEMS","ful_return",r,rows("ful_return_item").stream().anyMatch(i->i.n("return_id")==r.id()),"退货主单必须有明细");
            if(r.s("status").equals("RECEIVED"))relation("RETURN_ERP_HEAD","ful_return",r,o!=null&&e!=null&&e.live()&&e.n("status")==20&&e.n("order_id")==o.n("erp_order_id"),"已收货退货必须映射同源已审核ERP退货");
        }
        for(Row i:rows("ful_return_item")){
            Row r=get("ful_return",i.n("return_id")),s=get("ful_shipment_item",i.n("shipment_item_id")),o=get("ful_order_item",i.n("order_item_id"));
            relation("RETURN_ITEM_ORIGIN","ful_return_item",i,r!=null&&s!=null&&r.n("order_id")==i.n("order_id")&&r.n("shipment_id")==i.n("shipment_id")&&s.n("shipment_id")==i.n("shipment_id")&&s.n("order_item_id")==i.n("order_item_id"),"退货项关联原发货项身份，重复SKU也不能混用");
            if(received(i)){
                Row e=get("erp_sale_return_items",i.n("erp_sale_return_item_id")),l=get("erp_stock_record",i.n("erp_stock_record_id"));
                relation("RETURN_ERP_ITEM","ful_return_item",i,r!=null&&o!=null&&e!=null&&e.live()&&e.n("return_id")==r.n("erp_sale_return_id")&&e.n("order_item_id")==o.n("erp_order_item_id")&&e.n("product_id")==o.n("product_id")&&e.n("product_unit_id")==o.n("unit_id")&&e.n("warehouse_id")==r.n("warehouse_id")&&e.q("count").compareTo(i.q("quantity"))==0,"ERP退货项与原项、原仓、单位及数量一致");
                relation("RETURN_PHYSICAL","ful_return_item",i,r!=null&&o!=null&&l!=null&&l.n("biz_type")==60&&l.n("biz_id")==r.n("erp_sale_return_id")&&l.n("biz_item_id")==i.n("erp_sale_return_item_id")&&l.n("product_id")==o.n("product_id")&&l.n("warehouse_id")==r.n("warehouse_id")&&l.q("count").compareTo(i.q("quantity"))==0,"ERP唯一产生退货实物增加，必须映射同数量正流水");
            }else relation("RETURN_PREMATURE_MAPPING","ful_return_item",i,i.n("erp_sale_return_item_id")==0&&i.n("erp_stock_record_id")==0,"未收货退货不能存在ERP入库映射");
        }
        for(Row e:rows("erp_sale_return"))if(e.live()&&e.n("status")==20&&managedSource(e.n("order_id"))){
            relation("ERP_RETURN_UNMAPPED","erp_sale_return",e,rows("ful_return").stream().filter(r->r.s("status").equals("RECEIVED")&&r.n("erp_sale_return_id")==e.id()).count()==1,"托管源单已审核退货必须唯一映射已收货申请");
            for(Row i:rows("erp_sale_return_items"))if(i.live()&&i.n("return_id")==e.id())relation("ERP_RETURN_ITEM_UNMAPPED","erp_sale_return_items",i,rows("ful_return_item").stream().filter(r->received(r)&&r.n("erp_sale_return_item_id")==i.id()).count()==1,"已审核托管ERP退货项必须唯一映射");
        }
        for(Row l:rows("erp_stock_record")){
            boolean out=l.n("biz_type")==50||l.n("biz_type")==51,back=l.n("biz_type")==60||l.n("biz_type")==61;
            if(!out&&!back)continue;
            Row e=get(out?"erp_sale_out":"erp_sale_return",l.n("biz_id"));
            if(e==null||!managedSource(e.n("order_id")))continue;
            boolean mapped=out?l.n("biz_type")==50&&rows("ful_shipment_item").stream().anyMatch(i->i.n("erp_sale_out_item_id")==l.n("biz_item_id")&&same(get("ful_shipment",i.n("shipment_id")),"erp_sale_out_id",l.n("biz_id"))):l.n("biz_type")==60&&rows("ful_return_item").stream().anyMatch(i->received(i)&&i.n("erp_stock_record_id")==l.id());
            relation("MANAGED_PHYSICAL_UNMAPPED","erp_stock_record",l,mapped,"托管ERP实物流水必须有对应履约映射，不能出现手工撤销或额外退货流水");
        }
    }
}
