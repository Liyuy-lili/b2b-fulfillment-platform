package cn.iocoder.yudao.module.fulfillment.service;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.module.erp.dal.mysql.stock.ErpStockMapper;
import cn.iocoder.yudao.module.erp.dal.mysql.product.ErpProductMapper;
import cn.iocoder.yudao.module.erp.service.stock.ErpWarehouseService;
import cn.iocoder.yudao.module.fulfillment.controller.admin.AllocationContracts.AllocateRequest;
import cn.iocoder.yudao.module.fulfillment.controller.admin.ExecutionContracts.*;
import cn.iocoder.yudao.module.fulfillment.dal.dataobject.*;
import cn.iocoder.yudao.module.fulfillment.dal.mysql.*;
import cn.iocoder.yudao.module.fulfillment.domain.AllocationPlanner;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.fulfillment.enums.FulfillmentErrors.*;
@Service @RequiredArgsConstructor
public class FulWorkbenchService {
    private final FulWarehouseAccess warehouseAccess;
    private final FulOrderService orders;
    private final FulOrderItemMapper items;
    private final FulShipmentMapper shipments;
    private final FulShipmentItemMapper shipmentItems;
    private final FulCallbackEventMapper callbacks;
    private final FulCancellationMapper cancellations;
    private final ErpWarehouseService warehouses;
    private final ErpStockMapper stocks;
    private final ErpProductMapper products;

    @Transactional(readOnly=true)
    public PreviewResult preview(AllocateRequest request) {
        var order=orders.get(request.orderId());
        var ids=request.warehouseIds().stream().map(FulOrderService::parseId).sorted().toList();
        if(new HashSet<>(ids).size()!=ids.size()) throw exception(INVALID_COMMAND);
        warehouseAccess.require(warehouseAccess.actor(),ids,false);
        var warehouseList=warehouses.getWarehouseList(ids);
        if(warehouseList.size()!=ids.size() || warehouseList.stream().anyMatch(w->!Integer.valueOf(0).equals(w.getStatus()))) throw exception(WAREHOUSE_NOT_ACCESSIBLE);
        var demands=order.items().stream().filter(i->new BigDecimal(i.openQty()).signum()>0).map(i->{
            var product=products.selectById(Long.parseLong(i.productId()));
            if(product==null || !String.valueOf(product.getUnitId()).equals(i.unitId())) throw exception(INVALID_COMMAND);
            return new AllocationPlanner.Demand(Long.parseLong(i.id()),Long.parseLong(i.productId()),new BigDecimal(i.openQty()));
        }).toList();
        List<PreviewStock> views=new ArrayList<>();List<AllocationPlanner.Supply> supplies=new ArrayList<>();
        for(long product:demands.stream().map(AllocationPlanner.Demand::productId).distinct().sorted().toList()) {
            for(var wh:warehouseList.stream().sorted(Comparator.comparing(w->w.getId())).toList()) {
                var balance=stocks.snapshot(TenantContextHolder.getRequiredTenantId(),product,wh.getId());
                BigDecimal physical=balance==null?BigDecimal.ZERO:balance.getCount();
                BigDecimal reserved=balance==null?BigDecimal.ZERO:balance.getFulReservedCount();
                BigDecimal available=physical.subtract(reserved);
                views.add(new PreviewStock(String.valueOf(product),wh.getId().toString(),amount(physical),amount(reserved),amount(available)));
                supplies.add(new AllocationPlanner.Supply(product,wh.getId(),wh.getSort()==null?0L:wh.getSort(),available));
            }
        }
        var plan=AllocationPlanner.plan(demands,supplies,request.strategy());
        return new PreviewResult(request.strategy().name(),1,plan.sufficient(),plan.pieces().stream().map(p->new PreviewLine(String.valueOf(p.itemId()),String.valueOf(p.productId()),String.valueOf(p.warehouseId()),amount(p.quantity()))).toList(),views,"预览不锁定或承诺库存，正式分配会重新计算。");
    }
    public List<WarehouseView> warehouses() {
        var allowed=new HashSet<>(warehouseAccess.allowed(warehouseAccess.actor(),false));
        return warehouses.getWarehouseListByStatus(0).stream().filter(w->allowed.contains(w.getId())).sorted(Comparator.comparingLong((cn.iocoder.yudao.module.erp.dal.dataobject.stock.ErpWarehouseDO w)->w.getSort()==null?0L:w.getSort()).thenComparing(w->w.getId()))
                .map(w->new WarehouseView(w.getId().toString(),w.getName(),w.getSort())).toList();
    }
    public PageResult<ShipmentView> shipmentPage(String orderId,int pageNo,int pageSize) {
        orders.get(orderId);
        var allowed=warehouseAccess.allowed(warehouseAccess.actor(),false);if(allowed.isEmpty())return new PageResult<>(List.of(),0L);
        var page=shipments.selectPage(new Page<FulShipmentDO>(pageNo,pageSize),new LambdaQueryWrapperX<FulShipmentDO>()
                .eq(FulShipmentDO::getOrderId,FulOrderService.parseId(orderId)).in(FulShipmentDO::getWarehouseId,allowed).orderByDesc(FulShipmentDO::getId));
        return new PageResult<>(page.getRecords().stream().map(this::view).toList(),page.getTotal());
    }
    public ShipmentView shipment(String id) {
        var shipment=shipments.selectById(FulOrderService.parseId(id));
        if(shipment==null) throw exception(SHIPMENT_NOT_ACCESSIBLE);
        orders.get(shipment.getOrderId().toString());warehouseAccess.require(shipment.getWarehouseId(),false);return view(shipment);
    }
    public List<CancellationView> cancellations(String id) {
        orders.get(id);
        return cancellations.selectList(new LambdaQueryWrapperX<FulCancellationDO>().eq(FulCancellationDO::getOrderId,FulOrderService.parseId(id))
                .orderByDesc(FulCancellationDO::getId).last("LIMIT 100")).stream().map(c->new CancellationView(c.getId().toString(),c.getOrderItemId().toString(),amount(c.getQuantity()),c.getReason(),time(c.getCreateTime()))).toList();
    }
    private ShipmentView view(FulShipmentDO s) {
        var lines=shipmentItems.selectList(new LambdaQueryWrapperX<FulShipmentItemDO>().eq(FulShipmentItemDO::getShipmentId,s.getId()).orderByAsc(FulShipmentItemDO::getId))
                .stream().map(i->new ShipmentLine(i.getId().toString(),i.getOrderItemId().toString(),i.getReservationId().toString(),amount(i.getQuantity()),i.getErpSaleOutItemId().toString())).toList();
        var events=callbacks.selectList(new LambdaQueryWrapperX<FulCallbackEventDO>().eq(FulCallbackEventDO::getShipmentId,s.getId()).orderByDesc(FulCallbackEventDO::getId).last("LIMIT 100"))
                .stream().map(e->new CallbackView(e.getEventId(),e.getEventType(),e.getResult(),time(e.getOccurredAt()),time(e.getReceivedAt()),e.getConflictCount())).toList();
        return new ShipmentView(s.getId().toString(),s.getShipmentNo(),s.getOrderId().toString(),s.getWarehouseId().toString(),s.getErpSaleOutId().toString(),s.getStatus(),s.getCarrierCode(),s.getTrackingNo(),time(s.getShippedAt()),time(s.getDeliveredAt()),lines,events);
    }
    private static String amount(BigDecimal q) { return q.setScale(6).toPlainString(); }
    private static String time(LocalDateTime time) { return time==null?null:time.atOffset(ZoneOffset.UTC).toString(); }
}
