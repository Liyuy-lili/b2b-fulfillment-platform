package cn.iocoder.yudao.module.erp.dal.mysql.stock;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.module.erp.controller.admin.stock.vo.stock.ErpStockPageReqVO;
import cn.iocoder.yudao.module.erp.dal.dataobject.stock.ErpStockDO;
import org.apache.ibatis.annotations.Mapper;

import java.math.BigDecimal;

/**
 * ERP 产品库存 Mapper
 *
 * @author 芋道源码
 */
@Mapper
public interface ErpStockMapper extends BaseMapperX<ErpStockDO> {
    @com.baomidou.mybatisplus.annotation.InterceptorIgnore(tenantLine="true")
    @org.apache.ibatis.annotations.Select("SELECT id,product_id,warehouse_id,`count`,ful_reserved_count FROM erp_stock WHERE tenant_id=#{tenant} AND product_id=#{product} AND warehouse_id=#{warehouse} AND deleted=0")
    StockBalance snapshot(@org.apache.ibatis.annotations.Param("tenant") long tenant,
                @org.apache.ibatis.annotations.Param("product") long product,
                @org.apache.ibatis.annotations.Param("warehouse") long warehouse);

    default PageResult<ErpStockDO> selectPage(ErpStockPageReqVO reqVO) {
        return selectPage(reqVO, new LambdaQueryWrapperX<ErpStockDO>()
                .eqIfPresent(ErpStockDO::getProductId, reqVO.getProductId())
                .eqIfPresent(ErpStockDO::getWarehouseId, reqVO.getWarehouseId())
                .orderByDesc(ErpStockDO::getId));
    }

    default ErpStockDO selectByProductIdAndWarehouseId(Long productId, Long warehouseId) {
        return selectOne(ErpStockDO::getProductId, productId,
                ErpStockDO::getWarehouseId, warehouseId);
    }

    @com.baomidou.mybatisplus.annotation.InterceptorIgnore(tenantLine="true")
    @org.apache.ibatis.annotations.Insert("INSERT INTO erp_stock (tenant_id,product_id,warehouse_id,`count`,ful_reserved_count,creator,updater) VALUES (#{tenant},#{product},#{warehouse},0,0,#{actor},#{actor}) ON DUPLICATE KEY UPDATE id=id")
    void ensure(@org.apache.ibatis.annotations.Param("tenant") long tenant,
                @org.apache.ibatis.annotations.Param("product") long product,
                @org.apache.ibatis.annotations.Param("warehouse") long warehouse,
                @org.apache.ibatis.annotations.Param("actor") String actor);

    @com.baomidou.mybatisplus.annotation.InterceptorIgnore(tenantLine="true")
    @org.apache.ibatis.annotations.Select("SELECT id,product_id,warehouse_id,`count`,ful_reserved_count FROM erp_stock WHERE tenant_id=#{tenant} AND product_id=#{product} AND warehouse_id=#{warehouse} AND deleted=0 FOR UPDATE")
    StockBalance lock(@org.apache.ibatis.annotations.Param("tenant") long tenant,
                @org.apache.ibatis.annotations.Param("product") long product,
                @org.apache.ibatis.annotations.Param("warehouse") long warehouse);

    @com.baomidou.mybatisplus.annotation.InterceptorIgnore(tenantLine="true")
    @org.apache.ibatis.annotations.Update("UPDATE erp_stock SET `count`=`count`+#{delta},update_time=CURRENT_TIMESTAMP WHERE tenant_id=#{tenant} AND id=#{id} AND deleted=0 AND `count`+#{delta}>=ful_reserved_count")
    int changePhysical(@org.apache.ibatis.annotations.Param("tenant") long tenant,
                @org.apache.ibatis.annotations.Param("id") long id,@org.apache.ibatis.annotations.Param("delta") BigDecimal delta);

    @com.baomidou.mybatisplus.annotation.InterceptorIgnore(tenantLine="true")
    @org.apache.ibatis.annotations.Update("UPDATE erp_stock SET ful_reserved_count=ful_reserved_count+#{delta},update_time=CURRENT_TIMESTAMP WHERE tenant_id=#{tenant} AND id=#{id} AND deleted=0 AND ful_reserved_count+#{delta}>=0 AND ful_reserved_count+#{delta}<=`count`")
    int changeReserved(@org.apache.ibatis.annotations.Param("tenant") long tenant,
                @org.apache.ibatis.annotations.Param("id") long id,@org.apache.ibatis.annotations.Param("delta") BigDecimal delta);

    @org.apache.ibatis.annotations.Select("SELECT COALESCE(SUM(`count`),0) FROM erp_stock WHERE product_id=#{product} AND deleted=0")
    BigDecimal selectSumByProductId(@org.apache.ibatis.annotations.Param("product") Long productId);
}
