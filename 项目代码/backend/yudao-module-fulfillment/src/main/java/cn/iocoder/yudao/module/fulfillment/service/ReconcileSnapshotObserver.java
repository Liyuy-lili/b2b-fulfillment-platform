package cn.iocoder.yudao.module.fulfillment.service;
/** Internal test seam only; production has no implementation. */
public interface ReconcileSnapshotObserver {
    default void afterTable(String table) {}
    default void afterPersist() {}
}
