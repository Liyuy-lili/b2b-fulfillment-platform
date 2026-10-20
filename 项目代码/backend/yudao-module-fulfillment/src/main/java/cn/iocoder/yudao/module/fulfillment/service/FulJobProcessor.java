package cn.iocoder.yudao.module.fulfillment.service;

import cn.iocoder.yudao.module.fulfillment.domain.ImportCsv;
import cn.iocoder.yudao.module.fulfillment.framework.FileJobProperties;
import cn.iocoder.yudao.module.erp.service.stock.DatabaseCommandRetry;
import cn.iocoder.yudao.framework.common.exception.ServiceException;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;
import java.nio.file.Files;
import java.nio.charset.StandardCharsets;
import java.util.*;
import static cn.iocoder.yudao.module.fulfillment.service.JobValues.*;

@Service @RequiredArgsConstructor
public class FulJobProcessor {
    private final FulJobStore store;private final FulPrivateFiles files;private final FulJobAuthorization auth;
    private final FulDraftImport importer;private final FulJobExport exporter;private final FileJobProperties properties;
    private final FulOperationAudit audit;private final DatabaseCommandRetry retry;private final ObjectProvider<FulJobFault> faults;
    public void run(FulJobStore.Lease lease)throws Exception {
        auth.check(lease.job());store.renew(lease);
        FulPrivateFiles.Sealed result=null,errors=null;
        if(text(lease.job(),"job_type").equals("IMPORT")){
            var source=files.verified(files.metadata(lease.tenant(),text(lease.job(),"input_file_id")));
            if(!flag(lease.job(),"prepared")){
                try(var csv=new ImportCsv(Files.newInputStream(source))){
                    int cursor=(int)number(lease.job(),"parse_cursor");var chunk=new ArrayList<FulJobStore.InputRow>();
                    for(ImportCsv.Row row;(row=csv.next())!=null;){
                        if(Thread.currentThread().isInterrupted())throw new InterruptedException();
                        if(row.number()>properties.getImportMaxRows())throw new PermanentFailure("IMPORT_ROW_LIMIT");
                        if(row.number()<=cursor)continue;
                        String raw=audit.json(row.fields()),error=row.oversized()?"FIELD_SIZE_LIMIT":row.fields().size()!=5?"EXPECTED_FIVE_COLUMNS":null;
                        if(raw.getBytes(StandardCharsets.UTF_8).length>4096){raw="[]";error="FIELD_SIZE_LIMIT";}
                        String external=row.fields().isEmpty()?"":row.fields().get(0);if(external.length()>128){external=external.substring(0,128);error="EXTERNAL_NO_SIZE_LIMIT";}
                        chunk.add(new FulJobStore.InputRow(row.number(),raw,external,error));
                        if(chunk.size()>=properties.getBatchSize()){auth.check(lease.job());store.renew(lease);retry.run(()->{store.appendRows(lease,chunk);return true;});chunk.clear();}
                    }
                    if(!chunk.isEmpty()){auth.check(lease.job());store.renew(lease);store.appendRows(lease,chunk);}
                    store.prepared(lease);
                }
            }
            while(true){
                var rows=store.pendingRows(lease);if(rows.isEmpty())break;
                for(var row:rows){
                    if(Thread.currentThread().isInterrupted())throw new InterruptedException();auth.check(lease.job());store.renew(lease);int no=(int)number(row,"row_no");
                    try{retry.run(()->{importer.process(lease,no);return true;});}
                    catch(RowFailure error){store.rowFailed(lease,no,error.getMessage());}
                    catch(ServiceException error){store.rowFailed(lease,no,"ERP_VALIDATION_"+error.getCode());}
                    faults.orderedStream().forEach(f->f.afterRowCommit(lease.job(),no));
                }
            }
            errors=exporter.errorCsv(lease);
        }else result=exporter.workbook(lease);
        faults.orderedStream().forEach(f->f.beforeArtifactPublish(lease.job()));auth.check(lease.job());store.finish(lease,result,errors);
    }
}
