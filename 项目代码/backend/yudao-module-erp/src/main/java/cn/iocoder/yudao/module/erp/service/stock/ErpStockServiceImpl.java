package cn.iocoder.yudao.module.erp.service.stock;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.module.erp.controller.admin.stock.vo.stock.ErpStockPageReqVO;
import cn.iocoder.yudao.module.erp.dal.dataobject.stock.ErpStockDO;
import cn.iocoder.yudao.module.erp.dal.mysql.stock.ErpStockMapper;
import cn.iocoder.yudao.module.erp.service.product.ErpProductService;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

import java.math.BigDecimal;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.erp.enums.ErrorCodeConstants.STOCK_COUNT_NEGATIVE;
import static cn.iocoder.yudao.module.erp.enums.ErrorCodeConstants.STOCK_COUNT_NEGATIVE2;

/**
 * ERP 产品库存 Service 实现类
 *
 * @author 芋道源码
 */
@Service
@Validated
public class ErpStockServiceImpl implements ErpStockService {

    @Resource
    private ErpProductService productService;
    @Resource
    private ErpWarehouseService warehouseService;

    @Resource
    private ErpStockMapper stockMapper;

    @Override
    public ErpStockDO getStock(Long id) {
        return stockMapper.selectById(id);
    }

    @Override
    public ErpStockDO getStock(Long productId, Long warehouseId) {
        return stockMapper.selectByProductIdAndWarehouseId(productId, warehouseId);
    }

    @Override
    public BigDecimal getStockCount(Long productId) {
        BigDecimal count = stockMapper.selectSumByProductId(productId);
        return count != null ? count : BigDecimal.ZERO;
    }

    @Override
    public PageResult<ErpStockDO> getStockPage(ErpStockPageReqVO pageReqVO) {
        return stockMapper.selectPage(pageReqVO);
    }

    @Override
    public java.util.List<cn.iocoder.yudao.module.erp.dal.mysql.stock.StockBalance> lockStocks(
            java.util.Collection<cn.iocoder.yudao.module.erp.dal.mysql.stock.StockKey> keys,boolean createMissing) {
        if (!org.springframework.transaction.support.TransactionSynchronizationManager.isActualTransactionActive()) {
            throw new IllegalStateException("Stock locks require a business transaction");
        }
        long tenant=cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder.getRequiredTenantId();
        String actor=String.valueOf(cn.iocoder.yudao.framework.security.core.util.SecurityFrameworkUtils.getLoginUserId());
        java.util.List<cn.iocoder.yudao.module.erp.dal.mysql.stock.StockBalance> result=new java.util.ArrayList<>();
        keys.stream().distinct().sorted().forEach(key->{
            var balance=stockMapper.lock(tenant,key.productId(),key.warehouseId());
            if(balance==null && createMissing) {
                stockMapper.ensure(tenant,key.productId(),key.warehouseId(),actor);
                balance=stockMapper.lock(tenant,key.productId(),key.warehouseId());
            }
            if(balance!=null) result.add(balance);
        });
        return result;
    }

    @Override
    @org.springframework.transaction.annotation.Transactional(rollbackFor=Exception.class)
    public BigDecimal updateStockCountIncrement(Long productId, Long warehouseId, BigDecimal count) {
        var stock=lockStocks(java.util.List.of(new cn.iocoder.yudao.module.erp.dal.mysql.stock.StockKey(productId,warehouseId)),true).get(0);
        BigDecimal after=stock.getCount().add(count);
        if(after.compareTo(stock.getFulReservedCount())<0) {
            throw exception(STOCK_COUNT_NEGATIVE,productService.getProduct(productId).getName(),
                    warehouseService.getWarehouse(warehouseId).getName(),stock.available(),count);
        }
        long tenant=cn.iocoder.yudao.framework.tenant.core.context.TenantContextHolder.getRequiredTenantId();
        if(count.signum()!=0 && stockMapper.changePhysical(tenant,stock.getId(),count)!=1) {
            throw exception(STOCK_COUNT_NEGATIVE2,productService.getProduct(productId).getName(),warehouseService.getWarehouse(warehouseId).getName());
        }
        return after;
    }
}
