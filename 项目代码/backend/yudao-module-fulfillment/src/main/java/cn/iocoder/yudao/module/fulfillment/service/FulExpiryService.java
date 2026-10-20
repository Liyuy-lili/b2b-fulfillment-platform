package cn.iocoder.yudao.module.fulfillment.service;

import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.module.erp.dal.mysql.stock.ErpStockMapper;
import cn.iocoder.yudao.module.erp.dal.mysql.stock.StockKey;
import cn.iocoder.yudao.module.erp.service.sale.managed.ErpManagedOrderGuard;
import cn.iocoder.yudao.module.erp.service.stock.*;
import cn.iocoder.yudao.module.fulfillment.dal.dataobject.FulReservationDO;
import cn.iocoder.yudao.module.fulfillment.dal.mysql.*;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.fulfillment.enums.FulfillmentErrors.*;

/** Internal housekeeping command: no HTTP route and no impersonation of an administrator. */
@Service @RequiredArgsConstructor
public class FulExpiryService {
    private final FulCommandService commands;
    private final FulOutboxService outbox;
    private final FulAllocationService shared;
    private final FulOrderMapper orders;
    private final FulOrderItemMapper items;
    private final FulReservationMapper reservations;
    private final ErpManagedOrderGuard sourceGuard;
    private final ErpStockService stockService;
    private final ErpStockMapper stocks;
    private final ObjectProvider<ExpiryFault> faults;

    public interface ExpiryFault { void afterRelease(long reservationId); }
    public record ExpiryResult(String reservationId,String outcome,String releasedQty) {}
    public static class CandidateNotDueException extends RuntimeException {}

    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=15)
    public ExpiryResult expire(FulReservationDO candidate) {
        long tenant=TenantContextHolder.getRequiredTenantId();
        if(!Objects.equals(candidate.getTenantId(),tenant)) throw exception(ORDER_NOT_ACCESSIBLE);
        var command=commands.claimExpiry(candidate.getId());
        // The scan owns no reservation lock. Use exactly source -> order -> items -> reservations -> stock.
        var hint=orders.selectById(candidate.getOrderId());
        if(hint==null || sourceGuard.lockSource(hint.getErpOrderId())==null) throw exception(ORDER_NOT_ACCESSIBLE);
        var order=orders.lockById(tenant,hint.getId());
        if(order==null) throw exception(ORDER_NOT_ACCESSIBLE);
        if(command.getResponseJson()!=null) return commands.replay(command,ExpiryResult.class);
        var lines=items.lockItems(tenant,order.getId());
        var r=reservations.lockActive(tenant,order.getId()).stream()
                .filter(v->Objects.equals(v.getId(),candidate.getId())).findFirst().orElse(null);
        if(r==null) return commands.complete(command,new ExpiryResult(candidate.getId().toString(),"ALREADY_CLOSED","0.000000"));
        var balances=stockService.lockStocks(List.of(new StockKey(r.getProductId(),r.getWarehouseId())),false);
        LocalDateTime now=LocalDateTime.now(ZoneOffset.UTC);
        // Recheck AFTER every possible lock wait. A stale/future candidate must not save a terminal no-op.
        if(r.getExpireAt().isAfter(now)) throw new CandidateNotDueException();
        var item=lines.stream().filter(v->Objects.equals(v.getId(),r.getOrderItemId())).findFirst().orElseThrow(()->exception(STOCK_CONFLICT));
        if(!Objects.equals(item.getProductId(),r.getProductId()) || balances.size()!=1) throw exception(STOCK_CONFLICT);
        var balance=balances.get(0);BigDecimal amount=r.getHeldQty();
        if(stocks.changeReserved(tenant,balance.getId(),amount.negate())!=1) throw exception(STOCK_CONFLICT);
        r.setHeldQty(BigDecimal.ZERO).setReleasedQty(r.getReleasedQty().add(amount)).setActiveFlag(false).setVersion(r.getVersion()+1);
        r.setUpdateTime(now);r.setUpdater("0");reservations.updateById(r);
        item.setReservedQty(item.getReservedQty().subtract(amount)).setOpenQty(item.getOpenQty().add(amount));
        shared.persistItem(item,now,0L);
        order.setVersion(order.getVersion()+1);shared.persistOrder(order,lines,now,0L);
        shared.writeLedger("EXPIRE-"+r.getId(),1,r,amount.negate(),balance.getFulReservedCount().subtract(amount),
                "EXPIRE","Reservation deadline reached",now,0L);
        faults.orderedStream().forEach(f->f.afterRelease(r.getId()));
        outbox.append(order.getId(),cn.iocoder.yudao.module.fulfillment.domain.FulfillmentEvent.Type.RESERVATION_EXPIRED,command.getId());
        return commands.complete(command,new ExpiryResult(r.getId().toString(),"EXPIRED",amount.setScale(6).toPlainString()));
    }
}
