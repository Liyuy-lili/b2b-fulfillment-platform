package cn.iocoder.yudao.module.fulfillment.service;

import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils;
import cn.iocoder.yudao.module.erp.dal.mysql.stock.*;
import cn.iocoder.yudao.module.erp.service.stock.*;
import cn.iocoder.yudao.module.erp.service.sale.managed.ErpManagedSaleOutPort;
import cn.iocoder.yudao.module.fulfillment.controller.admin.ExecutionContracts.*;
import cn.iocoder.yudao.module.fulfillment.dal.dataobject.*;
import cn.iocoder.yudao.module.fulfillment.dal.mysql.*;
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
public class FulExecutionService {
    private final FulWarehouseAccess warehouseAccess;
    private final FulAllocationService shared;
    private final FulCommandService commands;
    private final FulOutboxService outbox;
    private final FulOrderItemMapper items;
    private final FulReservationMapper reservations;
    private final FulShipmentMapper shipments;
    private final FulShipmentItemMapper shipmentItems;
    private final FulCancellationMapper cancellations;
    private final FulStockLedgerMapper ledger;
    private final ErpStockMapper stocks;
    private final ErpStockService stockService;
    private final ErpWarehouseService warehouses;
    private final ErpManagedSaleOutPort erp;
    private final ObjectProvider<ShipmentFault> faults;
    public interface ShipmentFault { void afterErpApproved(); }

    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=20)
    public ShipResult ship(ShipRequest request,String key) {
        var amounts=amounts(request.items());long warehouse=FulOrderService.parseId(request.warehouseId());
        var command=commands.claim("SHIP",key,commands.canonical(List.of("SHIP:v1",request.orderId(),String.valueOf(warehouse),canonical(amounts),request.carrierCode().trim(),request.trackingNo().trim())));
        var order=shared.lockOrder(request.orderId(),"fulfillment:shipment:confirm");
        warehouseAccess.require(warehouse,true);warehouseAccess.reservations(order.getId(),amounts.keySet());
        if(command.getResponseJson()!=null) return commands.replay(command,ShipResult.class);
        var wh=warehouses.getWarehouse(warehouse);
        if(wh==null || !Integer.valueOf(0).equals(wh.getStatus())) throw exception(WAREHOUSE_NOT_ACCESSIBLE);
        long tenant=TenantContextHolder.getRequiredTenantId();
        var lines=items.lockItems(tenant,order.getId());
        var byItem=lines.stream().collect(Collectors.toMap(FulOrderItemDO::getId,Function.identity()));
        var held=reservations.lockActive(tenant,order.getId()).stream().collect(Collectors.toMap(FulReservationDO::getId,Function.identity()));
        for(var e:amounts.entrySet()) {
            var r=held.get(e.getKey());
            if(r==null || r.getWarehouseId()!=warehouse || e.getValue().compareTo(r.getHeldQty())>0) throw exception(RESERVATION_NOT_ACCESSIBLE);
            var item=byItem.get(r.getOrderItemId());
            if(item==null || !Objects.equals(item.getProductId(),r.getProductId())) throw exception(STOCK_CONFLICT);
        }
        var balances=stockService.lockStocks(amounts.keySet().stream().map(held::get).map(r->new StockKey(r.getProductId(),warehouse)).toList(),false)
                .stream().collect(Collectors.toMap(StockBalance::getProductId,Function.identity()));
        LocalDateTime now=LocalDateTime.now(ZoneOffset.UTC);
        if(amounts.keySet().stream().map(held::get).anyMatch(r->!r.getExpireAt().isAfter(now))) throw exception(RESERVATION_EXPIRED);
        Map<Long,BigDecimal> reservedAfter=new HashMap<>();
        List<ErpManagedSaleOutPort.Line> erpLines=new ArrayList<>();
        for(var e:amounts.entrySet()) {
            var r=held.get(e.getKey());var balance=balances.get(r.getProductId());var q=e.getValue();
            if(balance==null || stocks.changeReserved(tenant,balance.getId(),q.negate())!=1) throw exception(STOCK_CONFLICT);
            balance.setFulReservedCount(balance.getFulReservedCount().subtract(q));reservedAfter.put(r.getId(),balance.getFulReservedCount());
            r.setHeldQty(r.getHeldQty().subtract(q)).setConsumedQty(r.getConsumedQty().add(q)).setActiveFlag(r.getHeldQty().signum()>0).setVersion(r.getVersion()+1);
            r.setUpdateTime(now);r.setUpdater(String.valueOf(SecurityFrameworkUtils.getLoginUserId()));reservations.updateById(r);
            var item=byItem.get(r.getOrderItemId());item.setReservedQty(item.getReservedQty().subtract(q)).setShippedQty(item.getShippedQty().add(q));
            erpLines.add(new ErpManagedSaleOutPort.Line(r.getId(),item.getErpOrderItemId(),q));
        }
        // ERP is the only writer of H. Its REQUIRED/MANDATORY work joins this transaction.
        var out=erp.createAndApprove(new ErpManagedSaleOutPort.Request(order.getErpOrderId(),warehouse,erpLines));
        faults.orderedStream().forEach(ShipmentFault::afterErpApproved);
        var shipment=new FulShipmentDO().setShipmentNo("SHP-"+UUID.randomUUID()).setOrderId(order.getId()).setWarehouseId(warehouse)
                .setErpSaleOutId(out.saleOutId()).setStatus("SHIPPED").setCarrierCode(request.carrierCode().trim())
                .setTrackingNo(request.trackingNo().trim()).setShippedAt(now);
        shared.audit(shipment,now);shipments.insert(shipment);
        var mappings=out.mappings().stream().collect(Collectors.toMap(ErpManagedSaleOutPort.Mapping::reservationId,Function.identity()));
        int number=0;
        for(var e:amounts.entrySet()) {
            var r=held.get(e.getKey());var mapping=mappings.get(r.getId());
            if(mapping==null) throw exception(STOCK_CONFLICT);
            var line=new FulShipmentItemDO().setOrderId(order.getId()).setShipmentId(shipment.getId()).setOrderItemId(r.getOrderItemId())
                    .setReservationId(r.getId()).setQuantity(e.getValue()).setErpSaleOutItemId(mapping.saleOutItemId());
            shared.audit(line,now);shipmentItems.insert(line);
            var entry=new FulStockLedgerDO().setOperationNo(shipment.getShipmentNo()).setLineNo(++number).setReservationId(r.getId())
                    .setWarehouseId(warehouse).setProductId(r.getProductId()).setHeldDelta(e.getValue().negate()).setReservedAfter(reservedAfter.get(r.getId()))
                    .setEventType("SHIP").setReason("ERP approved shipment").setErpStockRecordId(mapping.stockRecordId()).setActorId(SecurityFrameworkUtils.getLoginUserId());
            shared.audit(entry,now);ledger.insert(entry);
        }
        lines.forEach(i->shared.persistItem(i,now));order.setVersion(order.getVersion()+1);shared.persistOrder(order,lines,now);
        outbox.append(order.getId(),cn.iocoder.yudao.module.fulfillment.domain.FulfillmentEvent.Type.SHIPMENT_CONFIRMED,command.getId());
        return commands.complete(command,new ShipResult(shipment.getId().toString(),shipment.getShipmentNo(),String.valueOf(out.saleOutId()),order.getStatus()));
    }

    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=20)
    public CancelResult cancel(CancelRequest request,String key) {
        var amounts=amounts(request.items());
        var command=commands.claim("CANCEL",key,commands.canonical(List.of("CANCEL:v1",request.orderId(),canonical(amounts),request.reason().trim())));
        var order=shared.lockOrder(request.orderId(),"fulfillment:order:cancel");
        warehouseAccess.cancellation(order.getId(),amounts.keySet());
        if(command.getResponseJson()!=null) return commands.replay(command,CancelResult.class);
        long tenant=TenantContextHolder.getRequiredTenantId();
        var lines=items.lockItems(tenant,order.getId());var byItem=lines.stream().collect(Collectors.toMap(FulOrderItemDO::getId,Function.identity()));
        for(var e:amounts.entrySet()) {
            var item=byItem.get(e.getKey());
            if(item==null || e.getValue().compareTo(item.getOpenQty().add(item.getReservedQty()))>0) throw exception(CANNOT_CANCEL);
        }
        var held=reservations.lockActive(tenant,order.getId());
        var balances=stockService.lockStocks(held.stream().filter(r->amounts.containsKey(r.getOrderItemId()))
                .map(r->new StockKey(r.getProductId(),r.getWarehouseId())).toList(),false).stream()
                .collect(Collectors.toMap(b->new StockKey(b.getProductId(),b.getWarehouseId()),Function.identity()));
        LocalDateTime now=LocalDateTime.now(ZoneOffset.UTC);String operation="CANCEL-"+UUID.randomUUID();int number=0;
        for(var e:amounts.entrySet()) {
            var item=byItem.get(e.getKey());BigDecimal fromOpen=item.getOpenQty().min(e.getValue());BigDecimal remaining=e.getValue().subtract(fromOpen);
            item.setOpenQty(item.getOpenQty().subtract(fromOpen));
            for(var r:held) {
                if(remaining.signum()==0) break;
                if(!Objects.equals(r.getOrderItemId(),item.getId())) continue;
                BigDecimal q=remaining.min(r.getHeldQty());var balance=balances.get(new StockKey(r.getProductId(),r.getWarehouseId()));
                if(balance==null || stocks.changeReserved(tenant,balance.getId(),q.negate())!=1) throw exception(STOCK_CONFLICT);
                balance.setFulReservedCount(balance.getFulReservedCount().subtract(q));
                r.setHeldQty(r.getHeldQty().subtract(q)).setReleasedQty(r.getReleasedQty().add(q)).setActiveFlag(r.getHeldQty().signum()>0).setVersion(r.getVersion()+1);
                r.setUpdateTime(now);r.setUpdater(String.valueOf(SecurityFrameworkUtils.getLoginUserId()));reservations.updateById(r);
                shared.writeLedger(operation,++number,r,q.negate(),balance.getFulReservedCount(),"CANCEL",request.reason().trim(),now);
                remaining=remaining.subtract(q);item.setReservedQty(item.getReservedQty().subtract(q));
            }
            if(remaining.signum()!=0) throw exception(STOCK_CONFLICT);
            item.setCancelledQty(item.getCancelledQty().add(e.getValue()));
            var fact=new FulCancellationDO().setOperationNo(operation).setOrderId(order.getId()).setOrderItemId(item.getId())
                    .setQuantity(e.getValue()).setReason(request.reason().trim()).setActorId(SecurityFrameworkUtils.getLoginUserId());
            shared.audit(fact,now);cancellations.insert(fact);
        }
        lines.forEach(i->shared.persistItem(i,now));order.setVersion(order.getVersion()+1);shared.persistOrder(order,lines,now);
        outbox.append(order.getId(),cn.iocoder.yudao.module.fulfillment.domain.FulfillmentEvent.Type.ORDER_CANCELLED,command.getId());
        return commands.complete(command,new CancelResult(order.getId().toString(),order.getStatus(),amounts.entrySet().stream()
                .map(e->new QuantityLine(e.getKey().toString(),e.getValue().toPlainString())).toList()));
    }
    private static TreeMap<Long,BigDecimal> amounts(List<QuantityLine> lines) {
        var result=new TreeMap<Long,BigDecimal>();
        for(var line:lines) if(result.put(FulOrderService.parseId(line.id()),FulAllocationService.quantity(line.quantity()))!=null) throw exception(INVALID_COMMAND);
        return result;
    }
    private static List<List<String>> canonical(Map<Long,BigDecimal> amounts) { return amounts.entrySet().stream().map(e->List.of(e.getKey().toString(),e.getValue().toPlainString())).toList(); }
}
