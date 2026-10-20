package cn.iocoder.yudao.module.fulfillment.service;
import cn.iocoder.yudao.module.fulfillment.domain.FulfillmentEvent.*;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;
import java.util.*;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.fulfillment.enums.FulfillmentErrors.*;
@Service @RequiredArgsConstructor
public class FulMessageSnapshots {
    private final JdbcTemplate jdbc;
    /** Called inside a business command holding its order lock, or the read-only rebuild proxy. */
    public Snapshot current(long tenant,long order){
        var heads=jdbc.queryForList("SELECT id,order_no,version,status FROM ful_order WHERE tenant_id=? AND id=? AND deleted=0",tenant,order);
        if(heads.isEmpty())throw exception(ORDER_NOT_ACCESSIBLE);
        var h=heads.get(0);var rows=jdbc.queryForList("SELECT id,product_id,unit_id,ordered_qty,open_qty,reserved_qty,shipped_qty,cancelled_qty,returned_qty FROM ful_order_item WHERE tenant_id=? AND order_id=? AND deleted=0 ORDER BY id LIMIT 1001",tenant,order);
        if(rows.isEmpty()||rows.size()>1000)throw exception(MESSAGE_TOO_LARGE);
        var items=rows.stream().map(r->new Item(s(r,"id"),s(r,"product_id"),s(r,"unit_id"),s(r,"ordered_qty"),s(r,"open_qty"),s(r,"reserved_qty"),s(r,"shipped_qty"),s(r,"cancelled_qty"),s(r,"returned_qty"))).toList();
        return new Snapshot(s(h,"id"),s(h,"order_no"),s(h,"version"),s(h,"status"),items);
    }
    @Transactional(propagation=Propagation.REQUIRES_NEW,readOnly=true,isolation=Isolation.REPEATABLE_READ,timeout=10)
    public Snapshot rebuildSnapshot(long tenant,long order){return current(tenant,order);}
    private static String s(Map<String,Object> r,String key){return r.get(key).toString();}
}
