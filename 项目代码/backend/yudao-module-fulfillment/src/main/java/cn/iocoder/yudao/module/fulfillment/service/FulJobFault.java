package cn.iocoder.yudao.module.fulfillment.service;
import java.util.Map;
public interface FulJobFault {
    default void afterClaim(Map<String,Object> job) {}
    default void afterRowBusiness(Map<String,Object> job,int row) {}
    default void afterRowCommit(Map<String,Object> job,int row) {}
    default void beforeArtifactPublish(Map<String,Object> job) {}
    default void afterContextCleared(Long tenant,Long actor) {}
}
