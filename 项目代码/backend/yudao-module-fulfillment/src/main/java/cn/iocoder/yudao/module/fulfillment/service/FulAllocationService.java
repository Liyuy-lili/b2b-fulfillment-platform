package cn.iocoder.yudao.module.fulfillment.service;

import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils;
import cn.iocoder.yudao.module.erp.dal.mysql.stock.*;
import cn.iocoder.yudao.module.erp.dal.mysql.product.ErpProductMapper;
import cn.iocoder.yudao.module.erp.service.stock.*;
import cn.iocoder.yudao.module.erp.service.sale.managed.ErpManagedOrderGuard;
import cn.iocoder.yudao.module.fulfillment.controller.admin.AllocationContracts.*;
import cn.iocoder.yudao.module.fulfillment.dal.dataobject.*;
import cn.iocoder.yudao.module.fulfillment.dal.mysql.*;
import cn.iocoder.yudao.module.fulfillment.domain.*;
import cn.iocoder.yudao.module.system.api.permission.PermissionApi;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;
import java.math.*;
import java.time.*;
import java.util.*;
import java.util.function.Function;
import java.util.stream.Collectors;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.framework.common.exception.enums.GlobalErrorCodeConstants.FORBIDDEN;
import static cn.iocoder.yudao.module.fulfillment.enums.FulfillmentErrors.*;

@Service
@RequiredArgsConstructor
public class FulAllocationService {
    private final FulWarehouseAccess warehouseAccess;
    private final FulCommandService commands;
    private final FulOutboxService outbox;
    private final FulOrderMapper orders;
    private final FulOrderItemMapper items;
    private final FulReservationMapper reservations;
    private final FulStockLedgerMapper ledger;
    private final ErpStockMapper stocks;
    private final ErpStockService stockService;
    private final ErpWarehouseService warehouses;
    private final ErpProductMapper products;
    private final ErpManagedOrderGuard sourceGuard;
    private final FulOrderService orderService;
    private final PermissionApi permissions;

    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=15)
    public AllocationResult allocate(AllocateRequest request,String key) {
        List<Long> warehouseIds=request.warehouseIds().stream().map(FulOrderService::parseId).sorted().toList();
        if(new HashSet<>(warehouseIds).size()!=warehouseIds.size()) throw exception(INVALID_COMMAND);
        var command=commands.claim("ALLOCATE",key,commands.canonical(List.of("ALLOCATE:v1",request.orderId(),request.strategy().name(),warehouseIds.stream().map(String::valueOf).toList(),request.holdSeconds())));
        var order=lockOrder(request.orderId(),"fulfillment:order:allocate");
        var warehouseList=warehouses.getWarehouseList(warehouseIds);
        if(warehouseList.size()!=warehouseIds.size() || warehouseList.stream().anyMatch(w->!Integer.valueOf(0).equals(w.getStatus()))) throw exception(WAREHOUSE_NOT_ACCESSIBLE);
        warehouseAccess.require(SecurityFrameworkUtils.getLoginUserId(),warehouseIds,true);
        if(command.getResponseJson()!=null) return commands.replay(command,AllocationResult.class);
        long tenant=TenantContextHolder.getRequiredTenantId();
        var lines=items.lockItems(tenant,order.getId());
        var demand=lines.stream().filter(i->i.getOpenQty().signum()>0).map(i->{
            var product=products.selectById(i.getProductId());
            if(product==null || !Objects.equals(product.getUnitId(),i.getUnitId())) throw exception(INVALID_COMMAND);
            return new AllocationPlanner.Demand(i.getId(),i.getProductId(),i.getOpenQty());
        }).toList();
        List<StockKey> keys=new ArrayList<>();
        demand.stream().map(AllocationPlanner.Demand::productId).distinct().forEach(p->warehouseIds.forEach(w->keys.add(new StockKey(p,w))));
        var balances=stockService.lockStocks(keys,false);
        Map<StockKey,StockBalance> balanceMap=balances.stream().collect(Collectors.toMap(b->new StockKey(b.getProductId(),b.getWarehouseId()),Function.identity()));
        Map<Long,Long> priority=warehouseList.stream().collect(Collectors.toMap(w->w.getId(),w->w.getSort()==null?0L:w.getSort()));
        var supply=balances.stream().map(b->new AllocationPlanner.Supply(b.getProductId(),b.getWarehouseId(),priority.get(b.getWarehouseId()),b.available())).toList();
        var plan=AllocationPlanner.plan(demand,supply,request.strategy());
        LocalDateTime now=LocalDateTime.now(ZoneOffset.UTC);
        List<ReservationView> created=new ArrayList<>();
        order.setAllocationAttempted(true).setAllocationStrategy(request.strategy().name()).setStrategyVersion(1).setVersion(order.getVersion()+1);
        if(plan.sufficient()) {
            String operation="ALLOC-"+UUID.randomUUID().toString();int lineNo=0;
            for(var piece:plan.pieces()) {
                StockBalance balance=balanceMap.get(new StockKey(piece.productId(),piece.warehouseId()));
                if(balance==null || stocks.changeReserved(tenant,balance.getId(),piece.quantity())!=1) throw exception(STOCK_CONFLICT);
                balance.setFulReservedCount(balance.getFulReservedCount().add(piece.quantity()));
                var reservation=new FulReservationDO().setReservationNo("RSV-"+UUID.randomUUID().toString())
                        .setOrderId(order.getId()).setOrderItemId(piece.itemId()).setProductId(piece.productId()).setWarehouseId(piece.warehouseId())
                        .setAllocationRound(Math.toIntExact(order.getVersion())).setAllocatedQty(piece.quantity()).setHeldQty(piece.quantity())
                        .setConsumedQty(BigDecimal.ZERO).setReleasedQty(BigDecimal.ZERO).setActiveFlag(true).setExpireAt(now.plusSeconds(request.holdSeconds())).setVersion(0L);
                audit(reservation,now);reservations.insert(reservation);
                writeLedger(operation,++lineNo,reservation,piece.quantity(),balance.getFulReservedCount(),"ALLOCATE",request.strategy().name(),now);
                created.add(view(reservation));
            }
            for(var item:lines) {
                if(item.getOpenQty().signum()==0) continue;
                item.setReservedQty(item.getReservedQty().add(item.getOpenQty())).setOpenQty(BigDecimal.ZERO);
                persistItem(item,now);
            }
        }
        persistOrder(order,lines,now);
        String outcome=demand.isEmpty()?"NOTHING_TO_ALLOCATE":plan.sufficient()?"ALLOCATED":"INSUFFICIENT_STOCK";
        outbox.append(order.getId(),plan.sufficient() && !created.isEmpty()?cn.iocoder.yudao.module.fulfillment.domain.FulfillmentEvent.Type.STOCK_RESERVED:cn.iocoder.yudao.module.fulfillment.domain.FulfillmentEvent.Type.ALLOCATION_ATTEMPTED,command.getId());
        return commands.complete(command,new AllocationResult(order.getId().toString(),order.getStatus(),outcome,created));
    }

    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=15)
    public ReleaseResult release(ReleaseRequest request,String key) {
        TreeMap<Long,BigDecimal> quantities=new TreeMap<>();
        for(var line:request.items()) {
            long id=FulOrderService.parseId(line.reservationId());
            BigDecimal quantity=quantity(line.quantity());
            if(quantities.put(id,quantity)!=null) throw exception(INVALID_COMMAND);
        }
        var canonicalLines=quantities.entrySet().stream().map(e->List.of(e.getKey().toString(),e.getValue().toPlainString())).toList();
        var command=commands.claim("RELEASE",key,commands.canonical(List.of("RELEASE:v1",request.orderId(),canonicalLines,request.reason().trim())));
        var order=lockOrder(request.orderId(),"fulfillment:order:release");
        warehouseAccess.reservations(order.getId(),quantities.keySet());
        if(command.getResponseJson()!=null) return commands.replay(command,ReleaseResult.class);
        long tenant=TenantContextHolder.getRequiredTenantId();
        var lines=items.lockItems(tenant,order.getId());
        Map<Long,FulOrderItemDO> itemMap=lines.stream().collect(Collectors.toMap(FulOrderItemDO::getId,Function.identity()));
        Map<Long,FulReservationDO> held=reservations.lockActive(tenant,order.getId()).stream().collect(Collectors.toMap(FulReservationDO::getId,Function.identity()));
        for(var e:quantities.entrySet()) {
            var r=held.get(e.getKey());
            if(r==null || e.getValue().compareTo(r.getHeldQty())>0) throw exception(RESERVATION_NOT_ACCESSIBLE);
        }
        var stockKeys=quantities.keySet().stream().map(held::get).map(r->new StockKey(r.getProductId(),r.getWarehouseId())).toList();
        var balances=stockService.lockStocks(stockKeys,false).stream().collect(Collectors.toMap(b->new StockKey(b.getProductId(),b.getWarehouseId()),Function.identity()));
        LocalDateTime now=LocalDateTime.now(ZoneOffset.UTC);String operation="RELEASE-"+UUID.randomUUID().toString();int lineNo=0;
        List<ReleasedLine> released=new ArrayList<>();
        for(var e:quantities.entrySet()) {
            var r=held.get(e.getKey());BigDecimal amount=e.getValue();
            var balance=balances.get(new StockKey(r.getProductId(),r.getWarehouseId()));
            if(balance==null || stocks.changeReserved(tenant,balance.getId(),amount.negate())!=1) throw exception(STOCK_CONFLICT);
            balance.setFulReservedCount(balance.getFulReservedCount().subtract(amount));
            r.setHeldQty(r.getHeldQty().subtract(amount)).setReleasedQty(r.getReleasedQty().add(amount)).setActiveFlag(r.getHeldQty().signum()>0).setVersion(r.getVersion()+1);
            r.setUpdateTime(now);r.setUpdater(String.valueOf(SecurityFrameworkUtils.getLoginUserId()));reservations.updateById(r);
            var item=itemMap.get(r.getOrderItemId());
            if(item==null || !Objects.equals(item.getProductId(),r.getProductId())) throw exception(STOCK_CONFLICT);
            item.setOpenQty(item.getOpenQty().add(amount)).setReservedQty(item.getReservedQty().subtract(amount));
            writeLedger(operation,++lineNo,r,amount.negate(),balance.getFulReservedCount(),"RELEASE",request.reason().trim(),now);
            released.add(new ReleasedLine(r.getId().toString(),amount.toPlainString()));
        }
        lines.forEach(i->persistItem(i,now));order.setVersion(order.getVersion()+1);
        persistOrder(order,lines,now);
        outbox.append(order.getId(),cn.iocoder.yudao.module.fulfillment.domain.FulfillmentEvent.Type.STOCK_RELEASED,command.getId());
        return commands.complete(command,new ReleaseResult(order.getId().toString(),order.getStatus(),released));
    }

    public List<ReservationView> reservationList(String id) {
        orderService.get(id); // Current read permission is enforced at the controller and owner scope here.
        var allowed=warehouseAccess.allowed(warehouseAccess.actor(),false);if(allowed.isEmpty())return List.of();
        return reservations.selectList(new LambdaQueryWrapperX<FulReservationDO>().eq(FulReservationDO::getOrderId,FulOrderService.parseId(id)).in(FulReservationDO::getWarehouseId,allowed).orderByAsc(FulReservationDO::getId)).stream().map(FulAllocationService::view).toList();
    }

    FulOrderDO lockOrder(String id,String permission) {
        long actor=SecurityFrameworkUtils.getLoginUserId();
        if(!permissions.hasAnyPermissions(actor,permission)) throw exception(FORBIDDEN);
        var hint=orders.selectById(FulOrderService.parseId(id));
        if(hint==null) throw exception(ORDER_NOT_ACCESSIBLE);
        if(sourceGuard.lockSource(hint.getErpOrderId())==null) throw exception(ORDER_NOT_ACCESSIBLE);
        var order=orders.lockById(TenantContextHolder.getRequiredTenantId(),hint.getId());
        if(order==null) throw exception(ORDER_NOT_ACCESSIBLE);
        orderService.requireOwner(order.getOwnerUserId());
        return order;
    }
    void persistOrder(FulOrderDO order,List<FulOrderItemDO> lines,LocalDateTime now) {
        persistOrder(order,lines,now,SecurityFrameworkUtils.getLoginUserId());
    }
    void persistOrder(FulOrderDO order,List<FulOrderItemDO> lines,LocalDateTime now,long actor) {
        order.setStatus(OrderStatusCalculator.calculate(lines.stream().map(FulAllocationService::quantities).toList(),order.getAllocationAttempted()).name());
        order.setUpdateTime(now);order.setUpdater(String.valueOf(actor));orders.updateById(order);
    }
    void persistItem(FulOrderItemDO item,LocalDateTime now) {
        persistItem(item,now,SecurityFrameworkUtils.getLoginUserId());
    }
    void persistItem(FulOrderItemDO item,LocalDateTime now,long actor) {
        quantities(item);item.setUpdateTime(now);item.setUpdater(String.valueOf(actor));items.updateById(item);
    }
    static OrderQuantities quantities(FulOrderItemDO i) { return new OrderQuantities(i.getOrderedQty(),i.getOpenQty(),i.getReservedQty(),i.getShippedQty(),i.getCancelledQty(),i.getReturnedQty()); }
    void audit(cn.iocoder.yudao.framework.tenant.core.db.TenantBaseDO value,LocalDateTime now) { FulOrderService.audit(value,TenantContextHolder.getRequiredTenantId(),SecurityFrameworkUtils.getLoginUserId(),now); }
    void writeLedger(String operation,int line,FulReservationDO r,BigDecimal delta,BigDecimal after,String type,String reason,LocalDateTime now) {
        writeLedger(operation,line,r,delta,after,type,reason,now,SecurityFrameworkUtils.getLoginUserId());
    }
    void writeLedger(String operation,int line,FulReservationDO r,BigDecimal delta,BigDecimal after,String type,String reason,LocalDateTime now,long actor) {
        var entry=new FulStockLedgerDO().setOperationNo(operation).setLineNo(line).setReservationId(r.getId()).setWarehouseId(r.getWarehouseId()).setProductId(r.getProductId()).setHeldDelta(delta).setReservedAfter(after).setEventType(type).setReason(reason).setActorId(actor);
        FulOrderService.audit(entry,TenantContextHolder.getRequiredTenantId(),actor,now);ledger.insert(entry);
    }
    static BigDecimal quantity(String value) {
        try { var q=new BigDecimal(value).setScale(6,RoundingMode.UNNECESSARY);if(q.signum()<=0 || q.precision()>24) throw new ArithmeticException();return q; }
        catch(RuntimeException e) { throw exception(INVALID_COMMAND); }
    }
    private static ReservationView view(FulReservationDO r) {
        return new ReservationView(r.getId().toString(),r.getOrderItemId().toString(),r.getProductId().toString(),r.getWarehouseId().toString(),r.getAllocatedQty().setScale(6).toPlainString(),r.getHeldQty().setScale(6).toPlainString(),r.getConsumedQty().setScale(6).toPlainString(),r.getReleasedQty().setScale(6).toPlainString(),r.getExpireAt().atOffset(ZoneOffset.UTC).toString());
    }
}
