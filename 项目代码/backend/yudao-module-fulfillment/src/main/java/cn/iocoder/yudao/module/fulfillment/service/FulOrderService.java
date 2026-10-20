package cn.iocoder.yudao.module.fulfillment.service;

import cn.hutool.crypto.digest.DigestUtil;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder;
import cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils;
import cn.iocoder.yudao.module.erp.dal.dataobject.sale.*;
import cn.iocoder.yudao.module.erp.dal.mysql.sale.ErpCustomerMapper;
import cn.iocoder.yudao.module.erp.dal.mysql.product.ErpProductMapper;
import cn.iocoder.yudao.module.erp.dal.mysql.product.ErpProductUnitMapper;
import cn.iocoder.yudao.module.erp.dal.mysql.finance.ErpAccountMapper;
import cn.iocoder.yudao.module.erp.enums.ErpAuditStatus;
import cn.iocoder.yudao.module.erp.service.sale.managed.ErpManagedOrderGuard;
import cn.iocoder.yudao.module.fulfillment.controller.admin.OrderContracts.*;
import cn.iocoder.yudao.module.fulfillment.dal.dataobject.*;
import cn.iocoder.yudao.module.fulfillment.dal.mysql.*;
import cn.iocoder.yudao.module.fulfillment.domain.*;
import cn.iocoder.yudao.module.system.api.permission.PermissionApi;
import cn.iocoder.yudao.module.system.api.user.AdminUserApi;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;
import java.math.BigDecimal;
import java.time.*;
import java.util.*;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.fulfillment.enums.FulfillmentErrors.*;

@Service
@RequiredArgsConstructor
public class FulOrderService {
    private final FulOrderMapper orders;
    private final FulOrderItemMapper items;
    private final FulCommandService commands;
    private final FulOutboxService outbox;
    private final ErpManagedOrderGuard sourceGuard;
    private final PermissionApi permissions;
    private final AdminUserApi users;
    private final ErpCustomerMapper customers;
    private final ErpProductMapper products;
    private final ErpProductUnitMapper units;
    private final ErpAccountMapper accounts;
    private final ObjectMapper json;

    @Transactional(rollbackFor=Exception.class, isolation=Isolation.READ_COMMITTED)
    public BindResult bind(BindRequest request, String key) {
        long tenant=TenantContextHolder.getRequiredTenantId();
        long actor=SecurityFrameworkUtils.getLoginUserId();
        if(!permissions.hasAnyPermissions(actor,"fulfillment:order:bind")) throw exception(cn.iocoder.yudao.framework.common.exception.enums.GlobalErrorCodeConstants.FORBIDDEN);
        long sourceId=parseId(request.erpOrderId());
        LocalDateTime now=LocalDateTime.now(ZoneOffset.UTC);
        FulCommandRecordDO command=commands.claim("BIND",key,"BIND:v1:"+sourceId);
        // Every old ERP writer uses this same source row lock before checking the policy.
        ErpSaleOrderDO source=sourceGuard.lockSource(sourceId);
        if (source==null) throw exception(ORDER_NOT_ACCESSIBLE);
        long owner=parseId(source.getCreator());
        requireOwner(owner);
        if (command.getResponseJson()!=null) {
            try {
                BindResult result=json.readValue(command.getResponseJson(),BindResult.class);
                accessibleOrder(parseId(result.orderId())); // Permissions/data scope are checked again on replay.
                return result;
            } catch (com.fasterxml.jackson.core.JsonProcessingException e) { throw new IllegalStateException("Invalid persisted command response",e); }
        }
        FulOrderDO existing=orders.lockBySource(tenant,sourceId);
        if (existing!=null) {
            requireOwner(existing.getOwnerUserId());
            return complete(command,new BindResult(existing.getId().toString(),existing.getStatus()),now);
        }
        if (!ErpAuditStatus.APPROVE.getStatus().equals(source.getStatus())) throw exception(SOURCE_ORDER_NOT_APPROVED);
        if (orders.findOutHistory(tenant,sourceId)!=null || orders.findReturnHistory(tenant,sourceId)!=null) {
            throw exception(SOURCE_ORDER_ALREADY_USED);
        }
        List<ErpSaleOrderItemDO> sourceItems=items.lockSourceItems(tenant,sourceId);
        if (sourceItems.isEmpty() || customers.selectById(source.getCustomerId())==null
                || users.getUser(owner)==null
                || (source.getAccountId()!=null && accounts.selectById(source.getAccountId())==null)
                || (source.getSaleUserId()!=null && users.getUser(source.getSaleUserId())==null)) throw exception(SOURCE_ORDER_INVALID);
        FulOrderDO order=new FulOrderDO().setErpOrderId(sourceId).setOrderNo(source.getNo())
                .setCustomerId(source.getCustomerId()).setOwnerUserId(owner).setAccountId(source.getAccountId())
                .setSaleUserId(source.getSaleUserId()).setStatus(OrderStatus.NEW.name()).setAllocationAttempted(false)
                .setAllocationStrategy("PRIORITY_SPLIT").setStrategyVersion(1).setVersion(0L)
                .setTotalPrice(decimal(source.getTotalPrice())).setDiscountPercent(decimal(source.getDiscountPercent()))
                .setDiscountPrice(decimal(source.getDiscountPrice())).setDepositPrice(decimal(source.getDepositPrice()));
        audit(order,tenant,actor,now);
        orders.insert(order);
        for (ErpSaleOrderItemDO sourceItem: sourceItems) {
            if (products.selectById(sourceItem.getProductId())==null || units.selectById(sourceItem.getProductUnitId())==null) throw exception(SOURCE_ORDER_INVALID);
            BigDecimal quantity=decimal(sourceItem.getCount());
            try { new OrderQuantities(quantity,quantity,BigDecimal.ZERO,BigDecimal.ZERO,BigDecimal.ZERO,BigDecimal.ZERO); }
            catch (IllegalArgumentException e) { throw exception(SOURCE_ORDER_INVALID); }
            FulOrderItemDO item=new FulOrderItemDO().setOrderId(order.getId()).setErpOrderItemId(sourceItem.getId())
                    .setProductId(sourceItem.getProductId()).setUnitId(sourceItem.getProductUnitId())
                    .setPriceSnapshot(decimal(sourceItem.getProductPrice())).setTaxPercent(decimal(sourceItem.getTaxPercent()))
                    .setTaxPrice(decimal(sourceItem.getTaxPrice())).setTotalPrice(decimal(sourceItem.getTotalPrice()))
                    .setOrderedQty(quantity).setOpenQty(quantity).setReservedQty(BigDecimal.ZERO).setShippedQty(BigDecimal.ZERO)
                    .setCancelledQty(BigDecimal.ZERO).setReturnedQty(BigDecimal.ZERO);
            audit(item,tenant,actor,now);
            items.insert(item);
        }
        outbox.append(order.getId(),cn.iocoder.yudao.module.fulfillment.domain.FulfillmentEvent.Type.ORDER_BOUND,command.getId());
        return complete(command,new BindResult(order.getId().toString(),order.getStatus()),now);
    }

    public OrderView get(String id) { return view(accessibleOrder(parseId(id)),true); }

    public PageResult<OrderView> page(PageRequest request) {
        var query=new LambdaQueryWrapperX<FulOrderDO>()
                .likeIfPresent(FulOrderDO::getOrderNo,request.getOrderNo())
                .eqIfPresent(FulOrderDO::getStatus,request.getStatus()).orderByDesc(FulOrderDO::getId);
        if (!isAdministrator()) query.eq(FulOrderDO::getOwnerUserId,SecurityFrameworkUtils.getLoginUserId());
        var page=orders.selectPage(request,query);
        return new PageResult<>(page.getList().stream().map(o->view(o,false)).toList(),page.getTotal());
    }

    private FulOrderDO accessibleOrder(long id) {
        FulOrderDO order=orders.selectById(id);
        if (order==null) throw exception(ORDER_NOT_ACCESSIBLE);
        requireOwner(order.getOwnerUserId());
        return order;
    }
    private boolean isAdministrator() { return permissions.hasAnyRoles(SecurityFrameworkUtils.getLoginUserId(),"super_admin","tenant_admin"); }
    void requireOwner(long owner) {
        if (owner!=SecurityFrameworkUtils.getLoginUserId() && !isAdministrator()) throw exception(ORDER_NOT_ACCESSIBLE);
    }
    private BindResult complete(FulCommandRecordDO command, BindResult result, LocalDateTime now) {
        return commands.complete(command,result);
    }
    static void audit(cn.iocoder.yudao.framework.tenant.core.db.TenantBaseDO value,long tenant,long actor,LocalDateTime now) {
        value.setTenantId(tenant);value.setCreator(Long.toString(actor));value.setUpdater(Long.toString(actor));
        value.setCreateTime(now);value.setUpdateTime(now);value.setDeleted(false);
    }
    static long parseId(String value) {
        try { long id=Long.parseLong(value);if(id<=0)throw new NumberFormatException();return id; }
        catch (RuntimeException e) { throw exception(SOURCE_ORDER_INVALID); }
    }
    private static BigDecimal decimal(BigDecimal value) {
        BigDecimal normalized=value==null?BigDecimal.ZERO:value;
        try { normalized=normalized.setScale(6,java.math.RoundingMode.UNNECESSARY); }
        catch (ArithmeticException e) { throw exception(SOURCE_ORDER_INVALID); }
        if(normalized.precision()>24) throw exception(SOURCE_ORDER_INVALID);
        return normalized;
    }
    private static String id(Long value) { return value==null?null:value.toString(); }
    private static String amount(BigDecimal value) { return value.toPlainString(); }

    private OrderView view(FulOrderDO o,boolean withItems) {
        List<ItemView> lines=withItems?items.selectList(new LambdaQueryWrapperX<FulOrderItemDO>()
                .eq(FulOrderItemDO::getOrderId,o.getId()).orderByAsc(FulOrderItemDO::getId)).stream()
                .map(i->new ItemView(id(i.getId()),id(i.getErpOrderItemId()),id(i.getProductId()),id(i.getUnitId()),
                        amount(i.getPriceSnapshot()),amount(i.getTaxPercent()),amount(i.getTaxPrice()),amount(i.getTotalPrice()),
                        amount(i.getOrderedQty()),amount(i.getOpenQty()),amount(i.getReservedQty()),amount(i.getShippedQty()),
                        amount(i.getCancelledQty()),amount(i.getReturnedQty()))).toList():List.of();
        return new OrderView(id(o.getId()),id(o.getErpOrderId()),o.getOrderNo(),id(o.getCustomerId()),id(o.getOwnerUserId()),
                id(o.getAccountId()),id(o.getSaleUserId()),o.getStatus(),o.getAllocationAttempted(),amount(o.getTotalPrice()),
                amount(o.getDiscountPercent()),amount(o.getDiscountPrice()),amount(o.getDepositPrice()),o.getCreateTime().atOffset(ZoneOffset.UTC).toString(),lines);
    }
}
