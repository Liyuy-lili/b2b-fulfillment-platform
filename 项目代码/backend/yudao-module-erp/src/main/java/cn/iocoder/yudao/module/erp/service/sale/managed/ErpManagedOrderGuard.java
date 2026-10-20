package cn.iocoder.yudao.module.erp.service.sale.managed;

import cn.iocoder.yudao.framework.common.exception.ErrorCode;
import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.module.erp.dal.dataobject.sale.ErpSaleOrderDO;
import cn.iocoder.yudao.module.erp.dal.mysql.sale.ErpSaleOrderMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import java.util.Collection;
import java.util.Objects;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;

@Component
@RequiredArgsConstructor
public class ErpManagedOrderGuard {
    public static final ErrorCode FROZEN = new ErrorCode(1_030_199_000, "MANAGED_ORDER_FROZEN: 销售单已托管，请通过履约入口操作");
    public static final ErrorCode CHANGED = new ErrorCode(1_030_199_001, "SOURCE_ORDER_CHANGED: 关联销售单已改变，请重新读取后重试");
    private final ErpSaleOrderMapper orderMapper;
    private final ObjectProvider<ErpManagedOrderPolicy> policies;

    public ErpSaleOrderDO lockSource(long id) {
        if (!TransactionSynchronizationManager.isActualTransactionActive()) {
            throw new IllegalStateException("ERP source lock requires an active transaction");
        }
        return orderMapper.selectForUpdate(TenantContextHolder.getRequiredTenantId(), id);
    }

    public java.util.Map<Long,ErpManagedOrderPolicy.Progress> progress(Collection<Long> sourceIds) {
        java.util.Map<Long,ErpManagedOrderPolicy.Progress> result=new java.util.HashMap<>();
        policies.orderedStream().forEach(p->result.putAll(p.progress(TenantContextHolder.getRequiredTenantId(),sourceIds)));
        return result;
    }
    public ErpSaleOrderDO requireManaged(long id) {
        var source=lockSource(id);
        if(source==null || policies.orderedStream().noneMatch(p->p.isManaged(TenantContextHolder.getRequiredTenantId(),id))) {
            throw exception(FROZEN);
        }
        return source;
    }

    public void assertMutable(long id) {
        lockSource(id);
        policies.orderedStream().forEach(p -> p.assertMutable(TenantContextHolder.getRequiredTenantId(), id));
    }

    public void assertMutable(Collection<Long> ids) {
        ids.stream().filter(Objects::nonNull).distinct().sorted().forEach(this::assertMutable);
    }
}
