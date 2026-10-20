package cn.iocoder.yudao.module.erp.service.sale.managed;

/** ERP owns this extension point; fulfillment implements it without reverse dependency. */
public interface ErpManagedOrderPolicy {
    void assertMutable(long tenantId, long orderId);
    default boolean isManaged(long tenantId,long orderId) { return false; }
    record ItemProgress(String remaining,String cancelled) {}
    record Progress(String fulfillmentId,java.util.Map<Long,ItemProgress> items) {}
    default java.util.Map<Long,Progress> progress(long tenant,java.util.Collection<Long> sourceIds) { return java.util.Map.of(); }
}
