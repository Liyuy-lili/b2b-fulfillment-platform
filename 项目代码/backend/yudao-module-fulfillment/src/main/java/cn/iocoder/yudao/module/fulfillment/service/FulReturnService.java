package cn.iocoder.yudao.module.fulfillment.service;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils;
import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.module.erp.dal.mysql.stock.StockKey;
import cn.iocoder.yudao.module.erp.service.stock.ErpStockService;
import cn.iocoder.yudao.module.erp.service.sale.managed.ErpManagedSaleReturnPort;
import cn.iocoder.yudao.module.fulfillment.controller.admin.ReturnContracts.*;
import cn.iocoder.yudao.module.fulfillment.dal.dataobject.*;
import cn.iocoder.yudao.module.fulfillment.dal.mysql.*;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;
import java.util.function.Function;
import java.util.stream.Collectors;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.fulfillment.enums.FulfillmentErrors.*;

@Service @RequiredArgsConstructor
public class FulReturnService {
    private final FulWarehouseAccess warehouseAccess;
    private final FulCommandService commands;
    private final FulOutboxService outbox;
    private final FulAllocationService shared;
    private final FulOrderService orderService;
    private final FulOrderItemMapper items;
    private final FulShipmentMapper shipments;
    private final FulShipmentItemMapper shipmentItems;
    private final FulReturnMapper returns;
    private final FulReturnItemMapper returnItems;
    private final ErpStockService stockService;
    private final ErpManagedSaleReturnPort erp;
    private final ObjectProvider<ReturnFault> faults;
    public interface ReturnFault { void afterErpApproved(); }

    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=20)
    public ReturnResult create(CreateRequest request,String key) {
        var amounts=new TreeMap<Long,BigDecimal>();
        for(var row:request.items()) if(amounts.put(FulOrderService.parseId(row.id()),FulAllocationService.quantity(row.quantity()))!=null) throw exception(INVALID_COMMAND);
        var canonical=amounts.entrySet().stream().map(e->List.of(e.getKey().toString(),e.getValue().toPlainString())).toList();
        var command=commands.claim("RETURN_CREATE",key,commands.canonical(List.of("RETURN_CREATE:v1",request.orderId(),request.shipmentId(),canonical,request.reason().trim())));
        var order=shared.lockOrder(request.orderId(),"fulfillment:return:create");
        warehouseAccess.shipment(order.getId(),FulOrderService.parseId(request.shipmentId()),true);
        if(command.getResponseJson()!=null) return commands.replay(command,ReturnResult.class);
        long tenant=TenantContextHolder.getRequiredTenantId();items.lockItems(tenant,order.getId());
        var shipment=lockShipment(order.getId(),FulOrderService.parseId(request.shipmentId()));
        var originals=shipmentItems.lockItems(tenant,shipment.getId()).stream().collect(Collectors.toMap(FulShipmentItemDO::getId,Function.identity()));
        for(var e:amounts.entrySet()) {
            var original=originals.get(e.getKey());
            if(original==null) throw exception(SHIPMENT_NOT_ACCESSIBLE);
            if(returnItems.committed(tenant,original.getId()).add(e.getValue()).compareTo(original.getQuantity())>0) throw exception(RETURN_QUANTITY_EXCEEDED);
        }
        LocalDateTime now=LocalDateTime.now(ZoneOffset.UTC);
        var head=new FulReturnDO().setReturnNo("RET-"+UUID.randomUUID()).setOrderId(order.getId()).setShipmentId(shipment.getId())
                .setWarehouseId(shipment.getWarehouseId()).setStatus("REQUESTED").setReason(request.reason().trim());
        shared.audit(head,now);returns.insert(head);
        for(var e:amounts.entrySet()) {
            var original=originals.get(e.getKey());
            var line=new FulReturnItemDO().setReturnId(head.getId()).setOrderId(order.getId()).setShipmentId(shipment.getId())
                    .setOrderItemId(original.getOrderItemId()).setShipmentItemId(original.getId()).setQuantity(e.getValue());
            shared.audit(line,now);returnItems.insert(line);
        }
        return commands.complete(command,result(head,order));
    }

    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=20)
    public ReturnResult receive(ReceiveRequest request,String key) {
        var command=commands.claim("RETURN_RECEIVE",key,commands.canonical(List.of("RETURN_RECEIVE:v1",request.orderId(),request.returnId())));
        var order=shared.lockOrder(request.orderId(),"fulfillment:return:receive");
        warehouseAccess.returned(order.getId(),FulOrderService.parseId(request.returnId()),true);
        if(command.getResponseJson()!=null) return commands.replay(command,ReturnResult.class);
        long tenant=TenantContextHolder.getRequiredTenantId();
        var lines=items.lockItems(tenant,order.getId());
        var hint=hint(order.getId(),request.returnId());var shipment=lockShipment(order.getId(),hint.getShipmentId());
        var originals=shipmentItems.lockItems(tenant,shipment.getId()).stream().collect(Collectors.toMap(FulShipmentItemDO::getId,Function.identity()));
        var head=returns.lock(tenant,order.getId(),hint.getId());
        if(head==null) throw exception(RETURN_NOT_ACCESSIBLE);
        if("REJECTED".equals(head.getStatus())) throw exception(RETURN_STATE_CONFLICT);
        if("RECEIVED".equals(head.getStatus())) return commands.complete(command,result(head,order));
        var rows=returnItems.lockItems(tenant,head.getId());
        if(rows.isEmpty()) throw exception(STOCK_CONFLICT);
        var byItem=lines.stream().collect(Collectors.toMap(FulOrderItemDO::getId,Function.identity()));
        List<ErpManagedSaleReturnPort.Line> requests=new ArrayList<>();List<StockKey> keys=new ArrayList<>();
        for(var row:rows) {
            var original=originals.get(row.getShipmentItemId());var item=byItem.get(row.getOrderItemId());
            if(original==null || item==null || !Objects.equals(original.getOrderItemId(),item.getId()) || row.getQuantity().signum()<=0
                    || returnItems.committed(tenant,original.getId()).compareTo(original.getQuantity())>0) throw exception(STOCK_CONFLICT);
            keys.add(new StockKey(item.getProductId(),shipment.getWarehouseId()));
            requests.add(new ErpManagedSaleReturnPort.Line(row.getId(),original.getErpSaleOutItemId(),row.getQuantity()));
        }
        stockService.lockStocks(keys,false);
        // The ERP adapter is the only writer of H, joining this transaction with MANDATORY propagation.
        var approved=erp.receiveAndApprove(new ErpManagedSaleReturnPort.Request(order.getErpOrderId(),shipment.getErpSaleOutId(),shipment.getWarehouseId(),requests));
        faults.orderedStream().forEach(ReturnFault::afterErpApproved);
        var mappings=approved.mappings().stream().collect(Collectors.toMap(ErpManagedSaleReturnPort.Mapping::returnItemId,Function.identity()));
        LocalDateTime now=LocalDateTime.now(ZoneOffset.UTC);
        for(var row:rows) {
            var mapping=mappings.get(row.getId());if(mapping==null) throw exception(STOCK_CONFLICT);
            row.setErpSaleReturnItemId(mapping.saleReturnItemId()).setErpStockRecordId(mapping.stockRecordId());
            row.setUpdateTime(now);row.setUpdater(String.valueOf(SecurityFrameworkUtils.getLoginUserId()));returnItems.updateById(row);
            var item=byItem.get(row.getOrderItemId());item.setReturnedQty(item.getReturnedQty().add(row.getQuantity()));
        }
        head.setStatus("RECEIVED").setErpSaleReturnId(approved.saleReturnId()).setReceivedAt(now).setReceivedBy(SecurityFrameworkUtils.getLoginUserId());
        head.setUpdateTime(now);head.setUpdater(String.valueOf(SecurityFrameworkUtils.getLoginUserId()));returns.updateById(head);
        lines.forEach(i->shared.persistItem(i,now));order.setVersion(order.getVersion()+1);shared.persistOrder(order,lines,now);
        outbox.append(order.getId(),cn.iocoder.yudao.module.fulfillment.domain.FulfillmentEvent.Type.RETURN_RECEIVED,command.getId());
        return commands.complete(command,result(head,order));
    }

    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=20)
    public ReturnResult reject(RejectRequest request,String key) {
        var command=commands.claim("RETURN_REJECT",key,commands.canonical(List.of("RETURN_REJECT:v1",request.orderId(),request.returnId(),request.reason().trim())));
        var order=shared.lockOrder(request.orderId(),"fulfillment:return:reject");
        warehouseAccess.returned(order.getId(),FulOrderService.parseId(request.returnId()),true);
        if(command.getResponseJson()!=null) return commands.replay(command,ReturnResult.class);
        long tenant=TenantContextHolder.getRequiredTenantId();items.lockItems(tenant,order.getId());
        var hint=hint(order.getId(),request.returnId());lockShipment(order.getId(),hint.getShipmentId());
        shipmentItems.lockItems(tenant,hint.getShipmentId());var head=returns.lock(tenant,order.getId(),hint.getId());
        if(head==null) throw exception(RETURN_NOT_ACCESSIBLE);
        if("RECEIVED".equals(head.getStatus())) throw exception(RETURN_STATE_CONFLICT);
        if("REJECTED".equals(head.getStatus())) return commands.complete(command,result(head,order));
        returnItems.lockItems(tenant,head.getId());LocalDateTime now=LocalDateTime.now(ZoneOffset.UTC);
        head.setStatus("REJECTED").setRejectedAt(now).setRejectedBy(SecurityFrameworkUtils.getLoginUserId()).setRejectionReason(request.reason().trim());
        head.setUpdateTime(now);head.setUpdater(String.valueOf(SecurityFrameworkUtils.getLoginUserId()));returns.updateById(head);
        return commands.complete(command,result(head,order));
    }

    public PageResult<ReturnView> page(String orderId,int pageNo,int pageSize) {
        orderService.get(orderId);
        var allowed=warehouseAccess.allowed(warehouseAccess.actor(),false);if(allowed.isEmpty())return new PageResult<>(List.of(),0L);
        var page=returns.selectPage(new Page<FulReturnDO>(pageNo,pageSize),new LambdaQueryWrapperX<FulReturnDO>()
                .eq(FulReturnDO::getOrderId,FulOrderService.parseId(orderId)).in(FulReturnDO::getWarehouseId,allowed).orderByDesc(FulReturnDO::getId));
        return new PageResult<>(page.getRecords().stream().map(this::view).toList(),page.getTotal());
    }
    public ReturnView get(String id) {
        var head=returns.selectById(FulOrderService.parseId(id));if(head==null) throw exception(RETURN_NOT_ACCESSIBLE);
        orderService.get(head.getOrderId().toString());warehouseAccess.require(head.getWarehouseId(),false);return view(head);
    }
    @Transactional(readOnly=true)
    public List<AllowanceLine> allowance(String orderId,String shipmentId) {
        orderService.get(orderId);
        var shipment=shipments.selectById(FulOrderService.parseId(shipmentId));
        if(shipment==null || !Objects.equals(shipment.getOrderId(),FulOrderService.parseId(orderId))) throw exception(SHIPMENT_NOT_ACCESSIBLE);
        warehouseAccess.require(shipment.getWarehouseId(),false);
        long tenant=TenantContextHolder.getRequiredTenantId();
        return shipmentItems.selectList(new LambdaQueryWrapperX<FulShipmentItemDO>().eq(FulShipmentItemDO::getShipmentId,shipment.getId()).orderByAsc(FulShipmentItemDO::getId))
                .stream().map(row->{
                    var committed=returnItems.committed(tenant,row.getId());
                    return new AllowanceLine(row.getId().toString(),row.getOrderItemId().toString(),row.getQuantity().setScale(6).toPlainString(),committed.setScale(6).toPlainString(),row.getQuantity().subtract(committed).setScale(6).toPlainString());
                }).toList();
    }
    private FulReturnDO hint(long order,String id) {
        var head=returns.selectById(FulOrderService.parseId(id));
        if(head==null || !Objects.equals(head.getOrderId(),order)) throw exception(RETURN_NOT_ACCESSIBLE);
        return head;
    }
    private FulShipmentDO lockShipment(long order,long id) {
        var head=shipments.lock(TenantContextHolder.getRequiredTenantId(),id);
        if(head==null || !Objects.equals(head.getOrderId(),order)) throw exception(SHIPMENT_NOT_ACCESSIBLE);
        return head;
    }
    private ReturnResult result(FulReturnDO r,FulOrderDO order) {return new ReturnResult(r.getId().toString(),r.getReturnNo(),r.getStatus(),id(r.getErpSaleReturnId()),order.getStatus());}
    private ReturnView view(FulReturnDO r) {
        var rows=returnItems.selectList(new LambdaQueryWrapperX<FulReturnItemDO>().eq(FulReturnItemDO::getReturnId,r.getId()).orderByAsc(FulReturnItemDO::getId))
                .stream().map(i->new ReturnLine(id(i.getId()),id(i.getShipmentItemId()),id(i.getOrderItemId()),i.getQuantity().setScale(6).toPlainString(),id(i.getErpSaleReturnItemId()),id(i.getErpStockRecordId()))).toList();
        return new ReturnView(id(r.getId()),r.getReturnNo(),id(r.getOrderId()),id(r.getShipmentId()),id(r.getWarehouseId()),r.getStatus(),r.getReason(),
                id(r.getErpSaleReturnId()),time(r.getReceivedAt()),time(r.getRejectedAt()),r.getRejectionReason(),time(r.getCreateTime()),rows);
    }
    private static String id(Long value) {return value==null?null:value.toString();}
    private static String time(LocalDateTime value) {return value==null?null:value.atOffset(ZoneOffset.UTC).toString();}
}
