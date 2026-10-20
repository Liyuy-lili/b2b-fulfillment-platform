package cn.iocoder.yudao.module.erp.service.sale;

import cn.hutool.core.collection.CollUtil;
import cn.hutool.core.util.ObjectUtil;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.number.MoneyUtils;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.module.erp.controller.admin.sale.vo.out.ErpSaleOutPageReqVO;
import cn.iocoder.yudao.module.erp.controller.admin.sale.vo.out.ErpSaleOutSaveReqVO;
import cn.iocoder.yudao.module.erp.dal.dataobject.product.ErpProductDO;
import cn.iocoder.yudao.module.erp.dal.dataobject.sale.ErpSaleOrderDO;
import cn.iocoder.yudao.module.erp.dal.dataobject.sale.ErpSaleOutDO;
import cn.iocoder.yudao.module.erp.dal.dataobject.sale.ErpSaleOutItemDO;
import cn.iocoder.yudao.module.erp.dal.mysql.sale.ErpSaleOutItemMapper;
import cn.iocoder.yudao.module.erp.dal.mysql.sale.ErpSaleOutMapper;
import cn.iocoder.yudao.module.erp.dal.redis.no.ErpNoRedisDAO;
import cn.iocoder.yudao.module.erp.enums.ErpAuditStatus;
import cn.iocoder.yudao.module.erp.enums.stock.ErpStockRecordBizTypeEnum;
import cn.iocoder.yudao.module.erp.service.finance.ErpAccountService;
import cn.iocoder.yudao.module.erp.service.product.ErpProductService;
import cn.iocoder.yudao.module.erp.service.stock.ErpStockRecordService;
import cn.iocoder.yudao.module.erp.service.stock.bo.ErpStockRecordCreateReqBO;
import cn.iocoder.yudao.module.system.api.user.AdminUserApi;
import jakarta.annotation.Resource;
import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;

import java.math.BigDecimal;
import java.util.Collection;
import java.util.Collections;
import java.util.List;
import java.util.Map;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.framework.common.util.collection.CollectionUtils.*;
import static cn.iocoder.yudao.module.erp.enums.ErrorCodeConstants.*;

// TODO 芋艿：记录操作日志

/**
 * ERP 销售出库 Service 实现类
 *
 * @author 芋道源码
 */
@Service
@Validated
public class ErpSaleOutServiceImpl implements ErpSaleOutService, cn.iocoder.yudao.module.erp.service.sale.managed.ErpManagedSaleOutPort {

    @Resource
    private cn.iocoder.yudao.module.erp.service.sale.managed.ErpManagedOrderGuard managedOrderGuard;


    @Resource
    private ErpSaleOutMapper saleOutMapper;
    @Resource
    private ErpSaleOutItemMapper saleOutItemMapper;

    @Resource
    private ErpNoRedisDAO noRedisDAO;

    @Resource
    private ErpProductService productService;
    @Resource
    @Lazy // 延迟加载，避免循环依赖
    private ErpSaleOrderService saleOrderService;
    @Resource
    private ErpAccountService accountService;
    @Resource
    private ErpStockRecordService stockRecordService;

    @Resource
    private AdminUserApi adminUserApi;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long createSaleOut(ErpSaleOutSaveReqVO createReqVO) {
        managedOrderGuard.assertMutable(createReqVO.getOrderId());
        return createSaleOutInternal(createReqVO,false);
    }

    private Long createSaleOutInternal(ErpSaleOutSaveReqVO createReqVO,boolean managed) {
        // 1.1 校验销售订单已审核
        ErpSaleOrderDO saleOrder = saleOrderService.validateSaleOrder(createReqVO.getOrderId());
        // 1.2 校验出库项的有效性
        List<ErpSaleOutItemDO> saleOutItems = validateSaleOutItems(createReqVO.getItems());
        // 1.3 校验结算账户
        accountService.validateAccount(createReqVO.getAccountId());
        // 1.4 校验销售人员
        if (createReqVO.getSaleUserId() != null) {
            adminUserApi.validateUser(createReqVO.getSaleUserId());
        }
        // 1.5 生成出库单号，并校验唯一性
        String no = noRedisDAO.generate(ErpNoRedisDAO.SALE_OUT_NO_PREFIX);
        if (saleOutMapper.selectByNo(no) != null) {
            throw exception(SALE_OUT_NO_EXISTS);
        }

        // 2.1 插入出库
        ErpSaleOutDO saleOut = BeanUtils.toBean(createReqVO, ErpSaleOutDO.class, in -> in
                .setNo(no).setStatus(ErpAuditStatus.PROCESS.getStatus()))
                .setOrderNo(saleOrder.getNo()).setCustomerId(saleOrder.getCustomerId());
        calculateTotalPrice(saleOut, saleOutItems);
        saleOutMapper.insert(saleOut);
        // 2.2 插入出库项
        saleOutItems.forEach(o -> o.setOutId(saleOut.getId()));
        saleOutItemMapper.insertBatch(saleOutItems);

        // 3. 更新销售订单的出库数量
        updateSaleOrderOutCount(createReqVO.getOrderId(),managed);
        return saleOut.getId();
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void updateSaleOut(ErpSaleOutSaveReqVO updateReqVO) {
        // 1.1 校验存在
        ErpSaleOutDO saleOut = lockMutableDocument(updateReqVO.getId(), updateReqVO.getOrderId());
        if (ErpAuditStatus.APPROVE.getStatus().equals(saleOut.getStatus())) {
            throw exception(SALE_OUT_UPDATE_FAIL_APPROVE, saleOut.getNo());
        }
        // 1.2 校验销售订单已审核
        ErpSaleOrderDO saleOrder = saleOrderService.validateSaleOrder(updateReqVO.getOrderId());
        // 1.3 校验结算账户
        accountService.validateAccount(updateReqVO.getAccountId());
        // 1.4 校验销售人员
        if (updateReqVO.getSaleUserId() != null) {
            adminUserApi.validateUser(updateReqVO.getSaleUserId());
        }
        // 1.5 校验订单项的有效性
        List<ErpSaleOutItemDO> saleOutItems = validateSaleOutItems(updateReqVO.getItems());

        // 2.1 更新出库
        ErpSaleOutDO updateObj = BeanUtils.toBean(updateReqVO, ErpSaleOutDO.class)
                .setOrderNo(saleOrder.getNo()).setCustomerId(saleOrder.getCustomerId());
        calculateTotalPrice(updateObj, saleOutItems);
        saleOutMapper.updateById(updateObj);
        // 2.2 更新出库项
        updateSaleOutItemList(updateReqVO.getId(), saleOutItems);

        // 3.1 更新销售订单的出库数量
        updateSaleOrderOutCount(updateObj.getOrderId());
        // 3.2 注意：如果销售订单编号变更了，需要更新“老”销售订单的出库数量
        if (ObjectUtil.notEqual(saleOut.getOrderId(), updateObj.getOrderId())) {
            updateSaleOrderOutCount(saleOut.getOrderId());
        }
    }

    private void calculateTotalPrice(ErpSaleOutDO saleOut, List<ErpSaleOutItemDO> saleOutItems) {
        saleOut.setTotalCount(getSumValue(saleOutItems, ErpSaleOutItemDO::getCount, BigDecimal::add));
        saleOut.setTotalProductPrice(getSumValue(saleOutItems, ErpSaleOutItemDO::getTotalPrice, BigDecimal::add, BigDecimal.ZERO));
        saleOut.setTotalTaxPrice(getSumValue(saleOutItems, ErpSaleOutItemDO::getTaxPrice, BigDecimal::add, BigDecimal.ZERO));
        saleOut.setTotalPrice(saleOut.getTotalProductPrice().add(saleOut.getTotalTaxPrice()));
        // 计算优惠价格
        if (saleOut.getDiscountPercent() == null) {
            saleOut.setDiscountPercent(BigDecimal.ZERO);
        }
        saleOut.setDiscountPrice(MoneyUtils.priceMultiplyPercent(saleOut.getTotalPrice(), saleOut.getDiscountPercent()));
        saleOut.setTotalPrice(saleOut.getTotalPrice().subtract(saleOut.getDiscountPrice()).add(saleOut.getOtherPrice()));
    }

    private void updateSaleOrderOutCount(Long orderId) { updateSaleOrderOutCount(orderId,false); }
    private void updateSaleOrderOutCount(Long orderId,boolean managed) {
        // 1.1 查询销售订单对应的销售出库单列表
        List<ErpSaleOutDO> saleOuts = saleOutMapper.selectListByOrderId(orderId);
        // 1.2 查询对应的销售订单项的出库数量
        Map<Long, BigDecimal> returnCountMap = saleOutItemMapper.selectOrderItemCountSumMapByOutIds(
                convertList(saleOuts, ErpSaleOutDO::getId));
        // 2. 更新销售订单的出库数量
        if(managed) saleOrderService.updateManagedSaleOrderOutCount(orderId,returnCountMap);
        else saleOrderService.updateSaleOrderOutCount(orderId, returnCountMap);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void updateSaleOutStatus(Long id, Integer status) {
        ErpSaleOutDO saleOut = lockMutableDocument(id, null);
        approveSaleOutInternal(saleOut,status);
    }

    private void approveSaleOutInternal(ErpSaleOutDO saleOut,Integer status) {
        Long id=saleOut.getId();
        boolean approve = ErpAuditStatus.APPROVE.getStatus().equals(status);
        // 1.2 校验状态
        if (saleOut.getStatus().equals(status)) {
            throw exception(approve ? SALE_OUT_APPROVE_FAIL : SALE_OUT_PROCESS_FAIL);
        }
        // 1.3 校验已退款
        if (!approve && saleOut.getReceiptPrice().compareTo(BigDecimal.ZERO) > 0) {
            throw exception(SALE_OUT_PROCESS_FAIL_EXISTS_RECEIPT);
        }

        // 2. 更新状态
        int updateCount = saleOutMapper.updateByIdAndStatus(id, saleOut.getStatus(),
                new ErpSaleOutDO().setStatus(status));
        if (updateCount == 0) {
            throw exception(approve ? SALE_OUT_APPROVE_FAIL : SALE_OUT_PROCESS_FAIL);
        }

        // 3. 变更库存
        List<ErpSaleOutItemDO> saleOutItems = saleOutItemMapper.selectListByOutId(id);
        Integer bizType = approve ? ErpStockRecordBizTypeEnum.SALE_OUT.getType()
                : ErpStockRecordBizTypeEnum.SALE_OUT_CANCEL.getType();
        java.util.List<ErpStockRecordCreateReqBO> stockChanges = new java.util.ArrayList<>();
        saleOutItems.forEach(saleOutItem -> {
            if (saleOutItem.getCount()==null || saleOutItem.getCount().signum()<=0) {
                throw exception(STOCK_DOCUMENT_QUANTITY_INVALID);
            }
            BigDecimal count = approve ? saleOutItem.getCount().negate() : saleOutItem.getCount();
            stockChanges.add(new ErpStockRecordCreateReqBO(
                    saleOutItem.getProductId(), saleOutItem.getWarehouseId(), count,
                    bizType, saleOutItem.getOutId(), saleOutItem.getId(), saleOut.getNo()));
        });
        stockRecordService.createStockRecords(stockChanges);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void updateSaleInReceiptPrice(Long id, BigDecimal receiptPrice) {
        ErpSaleOutDO saleOut = lockMutableDocument(id, null);
        if (saleOut.getReceiptPrice().equals(receiptPrice)) {
            return;
        }
        if (receiptPrice.compareTo(saleOut.getTotalPrice()) > 0) {
            throw exception(SALE_OUT_FAIL_RECEIPT_PRICE_EXCEED, receiptPrice,  saleOut.getTotalPrice());
        }
        saleOutMapper.updateById(new ErpSaleOutDO().setId(id).setReceiptPrice(receiptPrice));
    }

    @Resource private cn.iocoder.yudao.module.erp.dal.mysql.sale.ErpSaleOrderItemMapper managedSourceItems;
    @Resource private cn.iocoder.yudao.module.erp.service.stock.ErpWarehouseService managedWarehouses;
    @Resource private cn.iocoder.yudao.module.erp.dal.mysql.stock.ErpStockRecordMapper managedStockRecords;

    @Override
    @Transactional(propagation=org.springframework.transaction.annotation.Propagation.MANDATORY,rollbackFor=Exception.class)
    public cn.iocoder.yudao.module.erp.service.sale.managed.ErpManagedSaleOutPort.Result createAndApprove(
            cn.iocoder.yudao.module.erp.service.sale.managed.ErpManagedSaleOutPort.Request request) {
        var source=managedOrderGuard.requireManaged(request.sourceOrderId());
        if(!ErpAuditStatus.APPROVE.getStatus().equals(source.getStatus())) throw exception(SALE_ORDER_NOT_APPROVE);
        var warehouse=managedWarehouses.getWarehouse(request.warehouseId());
        if(warehouse==null || !Integer.valueOf(0).equals(warehouse.getStatus())) throw exception(STOCK_DOCUMENT_QUANTITY_INVALID);
        var sourceMap=managedSourceItems.selectListByOrderId(source.getId()).stream().collect(java.util.stream.Collectors.toMap(
                cn.iocoder.yudao.module.erp.dal.dataobject.sale.ErpSaleOrderItemDO::getId,java.util.function.Function.identity()));
        if(request.lines()==null || request.lines().isEmpty() || request.lines().size()>100) throw exception(STOCK_DOCUMENT_QUANTITY_INVALID);
        java.util.Set<Long> identities=new java.util.HashSet<>();
        var rows=new java.util.ArrayList<ErpSaleOutSaveReqVO.Item>();
        for(var line:request.lines()) {
            var item=sourceMap.get(line.sourceItemId());
            if(item==null || !identities.add(line.reservationId()) || line.quantity()==null || line.quantity().signum()<=0
                    || !java.util.Objects.equals(productService.getProduct(item.getProductId()).getUnitId(),item.getProductUnitId())) throw exception(STOCK_DOCUMENT_QUANTITY_INVALID);
            var row=new ErpSaleOutSaveReqVO.Item();row.setOrderItemId(item.getId());row.setWarehouseId(request.warehouseId());
            row.setProductId(item.getProductId());row.setProductUnitId(item.getProductUnitId());row.setProductPrice(item.getProductPrice());
            row.setTaxPercent(item.getTaxPercent()==null?BigDecimal.ZERO:item.getTaxPercent());row.setCount(line.quantity());
            row.setRemark("fulfillment:"+line.reservationId());rows.add(row);
        }
        var input=new ErpSaleOutSaveReqVO();input.setOrderId(source.getId());input.setAccountId(source.getAccountId());
        input.setSaleUserId(source.getSaleUserId());input.setOutTime(java.time.LocalDateTime.now());
        input.setDiscountPercent(source.getDiscountPercent());input.setOtherPrice(BigDecimal.ZERO);input.setItems(rows);
        input.setRemark("Managed fulfillment shipment");
        Long id=createSaleOutInternal(input,true);
        approveSaleOutInternal(lockCurrentDocument(id,source.getId()),ErpAuditStatus.APPROVE.getStatus());
        var actual=saleOutItemMapper.selectListByOutId(id);
        var result=new java.util.ArrayList<cn.iocoder.yudao.module.erp.service.sale.managed.ErpManagedSaleOutPort.Mapping>();
        for(var row:actual) {
            var stockRecord=managedStockRecords.selectOne(new cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX<cn.iocoder.yudao.module.erp.dal.dataobject.stock.ErpStockRecordDO>()
                    .eq(cn.iocoder.yudao.module.erp.dal.dataobject.stock.ErpStockRecordDO::getBizId,id)
                    .eq(cn.iocoder.yudao.module.erp.dal.dataobject.stock.ErpStockRecordDO::getBizItemId,row.getId())
                    .eq(cn.iocoder.yudao.module.erp.dal.dataobject.stock.ErpStockRecordDO::getBizType,ErpStockRecordBizTypeEnum.SALE_OUT.getType()));
            if(stockRecord==null) throw new IllegalStateException("ERP approval did not produce a stock record");
            result.add(new cn.iocoder.yudao.module.erp.service.sale.managed.ErpManagedSaleOutPort.Mapping(
                    Long.parseLong(row.getRemark().substring("fulfillment:".length())),row.getId(),stockRecord.getId()));
        }
        return new cn.iocoder.yudao.module.erp.service.sale.managed.ErpManagedSaleOutPort.Result(id,result);
    }

    private List<ErpSaleOutItemDO> validateSaleOutItems(List<ErpSaleOutSaveReqVO.Item> list) {
        // 1. 校验产品存在
        List<ErpProductDO> productList = productService.validProductList(
                convertSet(list, ErpSaleOutSaveReqVO.Item::getProductId));
        Map<Long, ErpProductDO> productMap = convertMap(productList, ErpProductDO::getId);
        // 2. 转化为 ErpSaleOutItemDO 列表
        return convertList(list, o -> BeanUtils.toBean(o, ErpSaleOutItemDO.class, item -> {
            item.setProductUnitId(productMap.get(item.getProductId()).getUnitId());
            item.setTotalPrice(MoneyUtils.priceMultiply(item.getProductPrice(), item.getCount()));
            if (item.getTotalPrice() == null) {
                return;
            }
            if (item.getTaxPercent() != null) {
                item.setTaxPrice(MoneyUtils.priceMultiplyPercent(item.getTotalPrice(), item.getTaxPercent()));
            }
        }));
    }

    private void updateSaleOutItemList(Long id, List<ErpSaleOutItemDO> newList) {
        // 第一步，对比新老数据，获得添加、修改、删除的列表
        List<ErpSaleOutItemDO> oldList = saleOutItemMapper.selectListByOutId(id);
        List<List<ErpSaleOutItemDO>> diffList = diffList(oldList, newList, // id 不同，就认为是不同的记录
                (oldVal, newVal) -> oldVal.getId().equals(newVal.getId()));

        // 第二步，批量添加、修改、删除
        if (CollUtil.isNotEmpty(diffList.get(0))) {
            diffList.get(0).forEach(o -> o.setOutId(id));
            saleOutItemMapper.insertBatch(diffList.get(0));
        }
        if (CollUtil.isNotEmpty(diffList.get(1))) {
            saleOutItemMapper.updateBatch(diffList.get(1));
        }
        if (CollUtil.isNotEmpty(diffList.get(2))) {
            saleOutItemMapper.deleteByIds(convertList(diffList.get(2), ErpSaleOutItemDO::getId));
        }
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deleteSaleOut(List<Long> ids) {
        // 1. 校验不处于已审批
        List<ErpSaleOutDO> saleOuts = saleOutMapper.selectByIds(ids);
        managedOrderGuard.assertMutable(saleOuts.stream().map(ErpSaleOutDO::getOrderId).toList());
        saleOuts = saleOuts.stream().sorted(java.util.Comparator.comparing(ErpSaleOutDO::getId))
                .map(old -> lockCurrentDocument(old.getId(), old.getOrderId())).toList();
        if (CollUtil.isEmpty(saleOuts)) {
            return;
        }
        saleOuts.forEach(saleOut -> {
            if (ErpAuditStatus.APPROVE.getStatus().equals(saleOut.getStatus())) {
                throw exception(SALE_OUT_DELETE_FAIL_APPROVE, saleOut.getNo());
            }
        });

        // 2. 遍历删除，并记录操作日志
        saleOuts.forEach(saleOut -> {
            // 2.1 删除订单
            saleOutMapper.deleteById(saleOut.getId());
            // 2.2 删除订单项
            saleOutItemMapper.deleteByOutId(saleOut.getId());

            // 2.3 更新销售订单的出库数量
            updateSaleOrderOutCount(saleOut.getOrderId());
        });

    }

    // Source order is always locked before its dependent document. Recheck the parent
    // with a current read: another writer may have moved it while this request waited.
    private ErpSaleOutDO lockMutableDocument(Long id, Long newOrderId) {
        ErpSaleOutDO old = validateSaleOutExists(id);
        managedOrderGuard.assertMutable(newOrderId == null ? java.util.List.of(old.getOrderId())
                : java.util.List.of(old.getOrderId(), newOrderId));
        return lockCurrentDocument(id, old.getOrderId());
    }

    private ErpSaleOutDO lockCurrentDocument(Long id, Long expectedOrderId) {
        ErpSaleOutDO current = saleOutMapper.selectForUpdate(
                cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder.getRequiredTenantId(), id);
        if (current == null) throw exception(SALE_OUT_NOT_EXISTS);
        if (!java.util.Objects.equals(current.getOrderId(), expectedOrderId)) {
            throw exception(cn.iocoder.yudao.module.erp.service.sale.managed.ErpManagedOrderGuard.CHANGED);
        }
        return current;
    }

    private ErpSaleOutDO validateSaleOutExists(Long id) {
        ErpSaleOutDO saleOut = saleOutMapper.selectById(id);
        if (saleOut == null) {
            throw exception(SALE_OUT_NOT_EXISTS);
        }
        return saleOut;
    }

    @Override
    public ErpSaleOutDO getSaleOut(Long id) {
        return saleOutMapper.selectById(id);
    }

    @Override
    public ErpSaleOutDO validateSaleOut(Long id) {
        ErpSaleOutDO saleOut = validateSaleOutExists(id);
        if (ObjectUtil.notEqual(saleOut.getStatus(), ErpAuditStatus.APPROVE.getStatus())) {
            throw exception(SALE_OUT_NOT_APPROVE);
        }
        return saleOut;
    }

    @Override
    public PageResult<ErpSaleOutDO> getSaleOutPage(ErpSaleOutPageReqVO pageReqVO) {
        return saleOutMapper.selectPage(pageReqVO);
    }

    // ==================== 销售出库项 ====================

    @Override
    public List<ErpSaleOutItemDO> getSaleOutItemListByOutId(Long outId) {
        return saleOutItemMapper.selectListByOutId(outId);
    }

    @Override
    public List<ErpSaleOutItemDO> getSaleOutItemListByOutIds(Collection<Long> outIds) {
        if (CollUtil.isEmpty(outIds)) {
            return Collections.emptyList();
        }
        return saleOutItemMapper.selectListByOutIds(outIds);
    }

    @Override
    public Long getSaleOutItemCountByProductId(Long productId) {
        return saleOutItemMapper.selectCount(ErpSaleOutItemDO::getProductId, productId);
    }

}
