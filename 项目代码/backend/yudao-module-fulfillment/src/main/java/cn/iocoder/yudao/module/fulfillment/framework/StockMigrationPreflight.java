package cn.iocoder.yudao.module.fulfillment.framework;

import org.flywaydb.core.api.FlywayException;
import org.flywaydb.core.api.callback.*;
import java.sql.*;
import java.util.*;

/** Runs before any migration DDL. Reports dirty identities without repairing facts. */
public class StockMigrationPreflight implements Callback {
    @Override public boolean supports(Event event,Context context) { return event==Event.BEFORE_MIGRATE; }
    @Override public boolean canHandleInTransaction(Event event,Context context) { return true; }
    @Override public String getCallbackName() { return "fulfillment-stock-preflight"; }
    @Override public void handle(Event event,Context context) {
        try {
            Connection c=context.getConnection();
            boolean hasReserved;
            try(var p=c.prepareStatement("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='erp_stock' AND COLUMN_NAME='ful_reserved_count'");var r=p.executeQuery()) {
                r.next();hasReserved=r.getInt(1)>0;
            }
            List<String> dirty=new ArrayList<>();
            String bad="`count`<0 OR deleted<>0 OR `count` IS NULL";
            if(hasReserved) bad+=" OR ful_reserved_count<0 OR ful_reserved_count>`count`";
            try(var p=c.prepareStatement("SELECT id,tenant_id,product_id,warehouse_id FROM erp_stock WHERE "+bad+" LIMIT 50");var r=p.executeQuery()) {
                while(r.next()) dirty.add("invalid stock id="+r.getLong(1)+",tenant="+r.getLong(2)+",product="+r.getLong(3)+",warehouse="+r.getLong(4));
            }
            try(var p=c.prepareStatement("SELECT tenant_id,product_id,warehouse_id,COUNT(*) FROM erp_stock GROUP BY tenant_id,product_id,warehouse_id HAVING COUNT(*)>1 LIMIT 50");var r=p.executeQuery()) {
                while(r.next()) dirty.add("duplicate tenant="+r.getLong(1)+",product="+r.getLong(2)+",warehouse="+r.getLong(3)+",rows="+r.getLong(4));
            }
            if(!dirty.isEmpty()) throw new FlywayException("STOCK_PREFLIGHT_REFUSED: "+dirty);
        } catch(SQLException e) { throw new FlywayException("Cannot verify stock migration preconditions",e); }
    }
}
