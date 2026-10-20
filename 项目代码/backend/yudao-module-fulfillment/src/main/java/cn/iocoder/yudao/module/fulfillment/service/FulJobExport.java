package cn.iocoder.yudao.module.fulfillment.service;

import cn.idev.excel.FastExcelFactory;
import cn.iocoder.yudao.module.fulfillment.framework.FileJobProperties;
import cn.iocoder.yudao.module.fulfillment.domain.ImportCsv;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import java.io.*;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.*;
import static cn.iocoder.yudao.module.fulfillment.service.JobValues.*;

@Service @RequiredArgsConstructor
public class FulJobExport {
    private final JdbcTemplate jdbc;private final FulJobAuthorization auth;
    private final FulPrivateFiles files;private final FulJobStore store;private final FileJobProperties properties;
    public long maximum(String dataset,long tenant){String table=switch(dataset){case "STOCK"->"erp_stock";case "ORDER"->"ful_order_item";case "SHIPMENT"->"ful_shipment_item";default->throw new IllegalArgumentException("Unsupported dataset");};return jdbc.queryForObject("SELECT COALESCE(MAX(id),0) FROM "+table+" WHERE tenant_id=?",Long.class,tenant);}
    private record Format(List<String> fields,List<String> headings) {}
    private Format format(String dataset){return switch(dataset){
        case "STOCK"->new Format(List.of("product_id","warehouse_id","physical","reserved","available"),List.of("商品编号","仓库编号","实物H","预占R","可用A"));
        case "ORDER"->new Format(List.of("order_id","order_no","status","product_id","unit_id","ordered_qty","open_qty","reserved_qty","shipped_qty","cancelled_qty","returned_qty","price_snapshot","total_price"),List.of("履约编号","销售单号","状态","商品编号","单位编号","订购","待分配","预占","发货","取消","退回","单价","明细金额"));
        case "SHIPMENT"->new Format(List.of("shipment_id","shipment_no","order_id","warehouse_id","status","product_id","quantity","tracking_no"),List.of("发货编号","发货单号","履约编号","仓库编号","状态","商品编号","发货数量","物流单号"));
        default->throw new PermanentFailure("EXPORT_DATASET_INVALID");};}
    private List<Map<String,Object>> batch(FulJobStore.Lease lease,long cursor){
        var job=lease.job();var scope=auth.scope(job);var args=new ArrayList<Object>();args.add(lease.tenant());args.add(cursor);args.add(number(job,"max_source_id"));String sql;
        switch(text(job,"dataset")){
            case "STOCK"->{sql="SELECT s.id AS cursor_id,s.product_id,s.warehouse_id,s.`count` AS physical,s.ful_reserved_count AS reserved,s.`count`-s.ful_reserved_count AS available FROM erp_stock s WHERE s.tenant_id=? AND s.id>? AND s.id<=? AND s.deleted=0 AND s.warehouse_id IN ("+marks(scope.warehouseIds().size())+")";args.addAll(scope.warehouseIds());sql+=" ORDER BY s.id LIMIT ?";}
            case "ORDER"->{sql="SELECT i.id AS cursor_id,o.id AS order_id,o.order_no,o.status,i.product_id,i.unit_id,i.ordered_qty,i.open_qty,i.reserved_qty,i.shipped_qty,i.cancelled_qty,i.returned_qty,i.price_snapshot,i.total_price FROM ful_order_item i JOIN ful_order o ON o.tenant_id=i.tenant_id AND o.id=i.order_id WHERE i.tenant_id=? AND i.id>? AND i.id<=? AND i.deleted=0 AND o.deleted=0";
                if(!scope.allOrders()){sql+=" AND o.owner_user_id=?";args.add(scope.ownerId());}if(scope.orderStatus()!=null){sql+=" AND o.status=?";args.add(scope.orderStatus());}sql+=" ORDER BY i.id LIMIT ?";}
            case "SHIPMENT"->{sql="SELECT i.id AS cursor_id,s.id AS shipment_id,s.shipment_no,s.order_id,s.warehouse_id,s.status,o.product_id,i.quantity,s.tracking_no FROM ful_shipment_item i JOIN ful_shipment s ON s.tenant_id=i.tenant_id AND s.id=i.shipment_id JOIN ful_order_item o ON o.tenant_id=i.tenant_id AND o.id=i.order_item_id WHERE i.tenant_id=? AND i.id>? AND i.id<=? AND i.deleted=0 AND s.deleted=0 AND o.deleted=0 AND s.warehouse_id IN ("+marks(scope.warehouseIds().size())+")";args.addAll(scope.warehouseIds());sql+=" ORDER BY i.id LIMIT ?";}
            default->throw new PermanentFailure("EXPORT_DATASET_INVALID");
        }
        args.add(properties.getBatchSize());return jdbc.queryForList(sql,args.toArray());
    }
    private String cell(Object value){return value==null?"":value instanceof BigDecimal d?d.setScale(6).toPlainString():String.valueOf(value);}
    public FulPrivateFiles.Sealed workbook(FulJobStore.Lease lease)throws Exception {
        String dataset=text(lease.job(),"dataset"),start=Instant.now().toString();var format=format(dataset);
        return files.write("xlsx","RESULT",output->{
            var writer=FastExcelFactory.write(output).autoCloseStream(false).inMemory(false).build();
            try{
                var sheet=FastExcelFactory.writerSheet(0,"数据").head(format.headings().stream().map(List::of).toList()).build();long cursor=0;int total=0;
                while(true){
                    if(Thread.currentThread().isInterrupted())throw new InterruptedException();auth.check(lease.job());store.renew(lease);
                    var rows=batch(lease,cursor);if(rows.isEmpty())break;
                    if((long)total+rows.size()>properties.getExportMaxRows())throw new PermanentFailure("EXPORT_ROW_LIMIT");
                    var values=rows.stream().map(r->format.fields().stream().map(k->cell(r.get(k))).toList()).toList();
                    // All cells are Java Strings: identifiers and formula-looking text stay text.
                    writer.write(values,sheet);total+=rows.size();cursor=number(rows.get(rows.size()-1),"cursor_id");store.exportProgress(lease,cursor,total);
                }
                var description=FastExcelFactory.writerSheet(1,"生成说明").head(List.of(List.of("项目"),List.of("值"))).build();
                writer.write(List.of(List.of("任务",String.valueOf(lease.id())),List.of("数据类型",dataset),List.of("生成开始",start),List.of("生成结束",Instant.now().toString()),List.of("初始最大ID",text(lease.job(),"max_source_id")),List.of("筛选与数据范围",text(lease.job(),"scope_json")),List.of("一致性边界","分批读取，非严格时点快照；生成期间原记录可能变化。"),List.of("单元格","标识、数量及文本均按文本输出。")),description);
            }finally{writer.finish();}
        });
    }
    public FulPrivateFiles.Sealed errorCsv(FulJobStore.Lease lease)throws Exception {
        if(jdbc.queryForObject("SELECT COUNT(*) FROM ful_file_job_row WHERE tenant_id=? AND job_id=? AND status='FAILED'",Long.class,lease.tenant(),lease.id())==0)return null;
        return files.write("csv","ERROR",output->{
            var writer=new BufferedWriter(new OutputStreamWriter(output,StandardCharsets.UTF_8));writer.write("rowNo,externalOrderNo,errorCode\r\n");int cursor=0;
            while(true){
                auth.check(lease.job());store.renew(lease);
                var rows=jdbc.queryForList("SELECT row_no,external_no,error_code FROM ful_file_job_row WHERE tenant_id=? AND job_id=? AND status='FAILED' AND row_no>? ORDER BY row_no LIMIT ?",lease.tenant(),lease.id(),cursor,properties.getBatchSize());if(rows.isEmpty())break;
                for(var row:rows){writer.write(ImportCsv.safeCell(text(row,"row_no"))+","+ImportCsv.safeCell(text(row,"external_no"))+","+ImportCsv.safeCell(text(row,"error_code"))+"\r\n");cursor=(int)number(row,"row_no");}
            }writer.flush();
        });
    }
}
