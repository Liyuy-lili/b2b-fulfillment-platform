package cn.iocoder.yudao.module.fulfillment.service;
/** Internal integration-test seam, no HTTP controls; production has no implementation. */
public interface FulMessageFault {
    default void beforeClaim() {}
    default void afterAppend(String type) {}
    default void afterBrokerConfirm(String eventId) {}
    default void afterProjection(String eventId) {}
    default void beforeAck(String eventId) {}
}
