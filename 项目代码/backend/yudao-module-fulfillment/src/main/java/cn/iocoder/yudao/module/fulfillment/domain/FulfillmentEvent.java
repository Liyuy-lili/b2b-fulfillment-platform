package cn.iocoder.yudao.module.fulfillment.domain;
import java.util.*;
/** Wire v1 uses strings for identifiers/versions/quantities; no customer or money fields. */
public record FulfillmentEvent(String eventId,String tenantId,String aggregateId,String aggregateVersion,
        Type eventType,int payloadVersion,String occurredAt,String traceId,Snapshot data) {
    public enum Type { ORDER_BOUND,STOCK_RESERVED,ALLOCATION_ATTEMPTED,STOCK_RELEASED,SHIPMENT_CONFIRMED,ORDER_CANCELLED,RESERVATION_EXPIRED,RETURN_RECEIVED }
    public record Item(String id,String productId,String unitId,String orderedQty,String openQty,String reservedQty,String shippedQty,String cancelledQty,String returnedQty) {}
    public record Snapshot(String orderId,String orderNo,String version,String status,List<Item> items) {}
    public void validate(){
        UUID.fromString(eventId);UUID.fromString(traceId);
        if(payloadVersion!=1||eventType==null||Long.parseLong(tenantId)<=0||Long.parseLong(aggregateId)<=0||Long.parseLong(aggregateVersion)<0||data==null||!aggregateId.equals(data.orderId())||!aggregateVersion.equals(data.version())||data.items()==null||data.items().isEmpty()||data.items().size()>1000)throw new IllegalArgumentException("Unsupported event identity/schema");
        java.time.Instant.parse(occurredAt);
    }
    public static long retryDelayMs(String eventId,int attempt,long baseMs){
        if(attempt<1||baseMs<50||baseMs>60000)throw new IllegalArgumentException("Invalid retry parameters");
        long ceiling=Math.min(60000,baseMs*(1L<<Math.min(attempt-1,10)));
        return Math.min(60000,ceiling+Math.floorMod(Objects.hash(eventId,attempt),Math.max(1,ceiling/5)));
    }
}
