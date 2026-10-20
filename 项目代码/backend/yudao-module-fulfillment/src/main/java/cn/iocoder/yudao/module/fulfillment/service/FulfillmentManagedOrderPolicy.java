package cn.iocoder.yudao.module.fulfillment.service;

import cn.iocoder.yudao.module.erp.service.sale.managed.ErpManagedOrderPolicy;
import cn.iocoder.yudao.module.erp.service.sale.managed.ErpManagedOrderGuard;
import cn.iocoder.yudao.module.fulfillment.dal.mysql.FulOrderMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;

@Component
@RequiredArgsConstructor
public class FulfillmentManagedOrderPolicy implements ErpManagedOrderPolicy {
    private final FulOrderMapper orderMapper;
    private final cn.iocoder.yudao.module.fulfillment.dal.mysql.FulOrderItemMapper itemMapper;
    @Override
    public java.util.Map<Long,Progress> progress(long tenant,java.util.Collection<Long> sources) {
        if(sources.isEmpty()) return java.util.Map.of();
        var orders=orderMapper.selectList(new cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX<cn.iocoder.yudao.module.fulfillment.dal.dataobject.FulOrderDO>()
                .in(cn.iocoder.yudao.module.fulfillment.dal.dataobject.FulOrderDO::getErpOrderId,sources));
        if(orders.isEmpty()) return java.util.Map.of();
        var items=itemMapper.selectList(new cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX<cn.iocoder.yudao.module.fulfillment.dal.dataobject.FulOrderItemDO>()
                .in(cn.iocoder.yudao.module.fulfillment.dal.dataobject.FulOrderItemDO::getOrderId,orders.stream().map(o->o.getId()).toList()));
        java.util.Map<Long,Progress> result=new java.util.HashMap<>();
        for(var order:orders) {
            java.util.Map<Long,ItemProgress> lines=new java.util.HashMap<>();
            items.stream().filter(i->i.getOrderId().equals(order.getId())).forEach(i->lines.put(i.getErpOrderItemId(),new ItemProgress(
                    i.getOpenQty().add(i.getReservedQty()).setScale(6).toPlainString(),i.getCancelledQty().setScale(6).toPlainString())));
            result.put(order.getErpOrderId(),new Progress(order.getId().toString(),lines));
        }
        return result;
    }
    @Override
    public boolean isManaged(long tenantId,long orderId) { return orderMapper.lockBySource(tenantId,orderId)!=null; }
    @Override
    public void assertMutable(long tenantId, long orderId) {
        if (orderMapper.lockBySource(tenantId,orderId) != null) throw exception(ErpManagedOrderGuard.FROZEN);
    }
}
