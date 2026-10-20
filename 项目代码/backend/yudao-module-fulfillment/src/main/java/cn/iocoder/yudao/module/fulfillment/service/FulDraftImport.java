package cn.iocoder.yudao.module.fulfillment.service;

import cn.hutool.crypto.digest.DigestUtil;
import cn.iocoder.yudao.module.erp.controller.admin.sale.vo.order.ErpSaleOrderSaveReqVO;
import cn.iocoder.yudao.module.erp.service.sale.ErpSaleOrderService;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;
import java.math.*;
import java.time.*;
import java.util.*;
import static cn.iocoder.yudao.module.fulfillment.service.JobValues.*;

@Service @RequiredArgsConstructor
public class FulDraftImport {
    private final JdbcTemplate jdbc;private final FulJobStore store;private final FulJobAuthorization auth;
    private final FulOperationAudit audit;private final ErpSaleOrderService erp;private final ObjectMapper json;private final ObjectProvider<FulJobFault> faults;
    public static BigDecimal decimal(String value,boolean positive){
        if(value==null||!value.matches("[0-9]{1,18}(\\.[0-9]{1,6})?"))throw new RowFailure("INVALID_DECIMAL");
        BigDecimal number=new BigDecimal(value).setScale(6,RoundingMode.UNNECESSARY);
        if(positive&&number.signum()==0)throw new RowFailure("QUANTITY_MUST_BE_POSITIVE");return number;
    }
    @Transactional(rollbackFor=Exception.class,isolation=Isolation.READ_COMMITTED,timeout=15)
    public void process(FulJobStore.Lease lease,int no){
        var job=store.lock(lease,false);auth.check(job);long actor=number(job,"actor_id");
        var row=jdbc.queryForMap("SELECT * FROM ful_file_job_row WHERE tenant_id=? AND job_id=? AND row_no=? FOR UPDATE",lease.tenant(),lease.id(),no);
        if(!text(row,"status").equals("PENDING"))return;
        List<String> values;try{values=json.readValue(text(row,"raw_json"),new TypeReference<List<String>>(){});}catch(Exception e){throw new RowFailure("INVALID_ROW_FORMAT");}
        if(values.size()!=5)throw new RowFailure("EXPECTED_FIVE_COLUMNS");
        String external=values.get(0).trim(),code=values.get(2).trim();
        if(external.isEmpty()||external.length()>128||external.chars().anyMatch(Character::isISOControl)||code.isEmpty()||code.length()>128)throw new RowFailure("INVALID_EXTERNAL_OR_PRODUCT_CODE");
        long customer;try{customer=Long.parseLong(values.get(1));if(customer<=0)throw new NumberFormatException();}catch(Exception e){throw new RowFailure("CUSTOMER_CODE_MUST_BE_INTERNAL_ID");}
        var quantity=decimal(values.get(3),true);var price=decimal(values.get(4),false);
        String hash=DigestUtil.sha256Hex(audit.json(List.of(String.valueOf(customer),code,quantity.toPlainString(),price.toPlainString())));
        jdbc.update("INSERT INTO ful_import_identity(tenant_id,source_system,external_no,request_hash,actor_id,job_id,row_no,created_at) VALUES(?,?,?,?,?,?,?,UTC_TIMESTAMP(6)) ON DUPLICATE KEY UPDATE id=id",lease.tenant(),text(job,"source_system"),external,hash,actor,lease.id(),no);
        var identity=jdbc.queryForMap("SELECT * FROM ful_import_identity WHERE tenant_id=? AND source_system=? AND external_no=? FOR UPDATE",lease.tenant(),text(job,"source_system"),external);
        if(!hash.equals(text(identity,"request_hash")))throw new RowFailure("EXTERNAL_ORDER_CONTENT_CONFLICT");
        if(number(identity,"actor_id")!=actor)throw new RowFailure("EXTERNAL_ORDER_OWNED_ELSEWHERE");
        Long order=identity.get("erp_order_id")==null?null:number(identity,"erp_order_id");String outcome="EXISTING";
        if(order==null){
            var products=jdbc.queryForList("SELECT id,unit_id FROM erp_product WHERE tenant_id=? AND bar_code=? AND status=0 AND deleted=0 LIMIT 2",lease.tenant(),code);
            if(products.size()!=1)throw new RowFailure("PRODUCT_CODE_NOT_UNIQUE_OR_DISABLED");
            if(jdbc.queryForObject("SELECT COUNT(*) FROM erp_customer WHERE tenant_id=? AND id=? AND status=0 AND deleted=0",Long.class,lease.tenant(),customer)!=1)throw new RowFailure("CUSTOMER_NOT_AVAILABLE");
            var product=products.get(0);var item=new ErpSaleOrderSaveReqVO.Item().setProductId(number(product,"id")).setProductUnitId(number(product,"unit_id")).setCount(quantity).setProductPrice(price).setTaxPercent(BigDecimal.ZERO);
            var request=new ErpSaleOrderSaveReqVO().setCustomerId(customer).setSaleUserId(actor).setOrderTime(LocalDateTime.now(ZoneOffset.UTC)).setDiscountPercent(BigDecimal.ZERO).setDepositPrice(BigDecimal.ZERO).setItems(List.of(item));
            order=erp.createSaleOrder(request);outcome="CREATED";
            jdbc.update("UPDATE ful_import_identity SET erp_order_id=? WHERE id=? AND tenant_id=?",order,number(identity,"id"),lease.tenant());
            faults.orderedStream().forEach(f->f.afterRowBusiness(job,no));
        }else if(jdbc.queryForObject("SELECT COUNT(*) FROM erp_sale_order WHERE tenant_id=? AND id=? AND deleted=0",Long.class,lease.tenant(),order)!=1)throw new RowFailure("EXISTING_DRAFT_REMOVED");
        store.lock(lease,false);auth.check(job);
        jdbc.update("UPDATE ful_file_job_row SET status='SUCCEEDED',erp_order_id=?,outcome=?,error_code=NULL,updated_at=UTC_TIMESTAMP(6) WHERE tenant_id=? AND job_id=? AND row_no=?",order,outcome,lease.tenant(),lease.id(),no);
        jdbc.update("UPDATE ful_file_job SET success_rows=success_rows+1 WHERE tenant_id=? AND id=?",lease.tenant(),lease.id());
    }
}
