package cn.iocoder.yudao.module.fulfillment.service;
import cn.iocoder.yudao.module.fulfillment.domain.ReconcileEngine;
import cn.iocoder.yudao.module.fulfillment.domain.ReconcileEngine.Row;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;
import java.time.LocalDateTime;
import java.util.*;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.fulfillment.enums.FulfillmentErrors.RECONCILE_LIMIT_EXCEEDED;

/** Separate bean: permission/idempotency reads cannot accidentally anchor this view.
 * REQUIRES_NEW only reads facts; the outer RC command transaction persists results.
 */
@Service @RequiredArgsConstructor
public class FulReconcileSnapshotReader {
    private static final List<String> TABLES=List.of("erp_stock","erp_stock_record","ful_order","ful_order_item","ful_reservation","ful_stock_ledger","ful_shipment","ful_shipment_item","ful_cancellation","ful_return","ful_return_item","erp_sale_order","erp_sale_order_items","erp_sale_out","erp_sale_out_items","erp_sale_return","erp_sale_return_items");
    private final JdbcTemplate jdbc;
    private final ObjectProvider<ReconcileSnapshotObserver> observer;
    @Value("${fulfillment.reconcile.row-limit:2000}") private int rowLimit;
    @Value("${fulfillment.reconcile.ledger-limit:10000}") private int ledgerLimit;
    @Value("${fulfillment.reconcile.difference-limit:2000}") private int differenceLimit;
    public record Snapshot(LocalDateTime at,Map<String,Integer> counts,int scanned,List<ReconcileEngine.Finding> findings) {}
    @Transactional(propagation=Propagation.REQUIRES_NEW,readOnly=true,isolation=Isolation.REPEATABLE_READ,timeout=15)
    public Snapshot read(long tenant){
        if(rowLimit<1||rowLimit>2000||ledgerLimit<1||ledgerLimit>10000||differenceLimit<1||differenceLimit>2000)throw new IllegalStateException("Invalid reconciliation bounds");
        LocalDateTime at=jdbc.queryForObject("SELECT UTC_TIMESTAMP(6)",LocalDateTime.class);
        Map<String,List<Row>> data=new LinkedHashMap<>();Map<String,Integer> counts=new LinkedHashMap<>();int scanned=0;
        for(String table:TABLES){
            int cap=Set.of("erp_stock_record","ful_stock_ledger").contains(table)?ledgerLimit:rowLimit;
            List<Row> all=new ArrayList<>();long cursor=0;
            while(true){
                int size=Math.min(200,cap+1-all.size());
                String index=Set.of("ful_order","ful_order_item","ful_reservation","ful_stock_ledger","ful_shipment","ful_shipment_item").contains(table)?"uk_tenant_id":"ix_reconcile_tenant_id";
                var page=jdbc.queryForList("SELECT * FROM "+table+" FORCE INDEX ("+index+") WHERE tenant_id=? AND id>? ORDER BY id LIMIT ?",tenant,cursor,size);
                for(var row:page)all.add(new Row(row));
                if(all.size()>cap)throw exception(RECONCILE_LIMIT_EXCEEDED);
                if(page.size()<size)break;
                cursor=((Number)page.get(page.size()-1).get("id")).longValue();
            }
            data.put(table,all);counts.put(table,all.size());scanned+=all.size();
            observer.ifAvailable(o->o.afterTable(table));
        }
        try{return new Snapshot(at,counts,scanned,new ReconcileEngine(data,differenceLimit).check());}
        catch(ReconcileEngine.LimitExceeded e){throw exception(RECONCILE_LIMIT_EXCEEDED);}
    }
}
