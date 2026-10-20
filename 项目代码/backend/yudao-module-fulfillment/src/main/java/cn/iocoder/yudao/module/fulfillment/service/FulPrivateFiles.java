package cn.iocoder.yudao.module.fulfillment.service;

import cn.iocoder.yudao.module.fulfillment.framework.FileJobProperties;
import lombok.RequiredArgsConstructor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.transaction.annotation.*;
import java.io.*;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import static cn.iocoder.yudao.module.fulfillment.service.JobValues.*;
import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.fulfillment.enums.FulfillmentErrors.FILE_INVALID;

@Service @RequiredArgsConstructor
public class FulPrivateFiles {
    private final FileJobProperties properties;private final JdbcTemplate jdbc;
    public record Sealed(String id,String key,String hash,long bytes,String kind,String name) {}
    @FunctionalInterface public interface Writer {void write(OutputStream stream)throws Exception;}
    private Path root()throws IOException {Path root=Path.of(properties.getStorageRoot()).toAbsolutePath().normalize();Files.createDirectories(root);return root.toRealPath();}
    public Path path(String key)throws IOException {
        if(key==null||!key.matches("[0-9a-f-]{36}\\.(csv|xlsx)"))throw new PermanentFailure("FILE_PATH_INVALID");
        Path root=root(),file=root.resolve(key).normalize();
        if(!file.getParent().equals(root)||Files.isSymbolicLink(file))throw new PermanentFailure("FILE_PATH_INVALID");return file;
    }
    public Sealed write(String ext,String kind,Writer writer)throws Exception {
        String id=UUID.randomUUID().toString(),key=id+"."+ext;Path destination=path(key);
        try{
            try(var stream=new LimitedOutput(Files.newOutputStream(destination,StandardOpenOption.CREATE_NEW),kind.equals("INPUT")?properties.getUploadMaxBytes():properties.getOutputMaxBytes())){writer.write(stream);}
            return new Sealed(id,key,hash(destination),Files.size(destination),kind,kind.toLowerCase(Locale.ROOT)+"."+ext);
        }catch(Exception e){Files.deleteIfExists(destination);throw e;}
    }
    public static String hash(Path file)throws Exception {
        var digest=MessageDigest.getInstance("SHA-256");try(var in=Files.newInputStream(file)){byte[] block=new byte[65536];for(int n;(n=in.read(block))!=-1;)digest.update(block,0,n);}return HexFormat.of().formatHex(digest.digest());
    }
    @Transactional(rollbackFor=Exception.class,timeout=20)
    public Sealed upload(MultipartFile file,long tenant,long actor)throws Exception {
        if(file.isEmpty()||file.getSize()>properties.getUploadMaxBytes()||file.getOriginalFilename()==null||!file.getOriginalFilename().toLowerCase(Locale.ROOT).endsWith(".csv"))throw exception(FILE_INVALID);
        Sealed result=write("csv","INPUT",out->{try(var input=file.getInputStream()){input.transferTo(out);}});register(result,tenant,actor);return result;
    }
    @Transactional(propagation=Propagation.MANDATORY)
    public void register(Sealed f,long tenant,long actor){
        jdbc.update("INSERT INTO ful_private_file(id,tenant_id,actor_id,kind,file_name,storage_key,sha256,byte_size,created_at) VALUES(?,?,?,?,?,?,?,?,UTC_TIMESTAMP(6))",f.id(),tenant,actor,f.kind(),f.name(),f.key(),f.hash(),f.bytes());
    }
    public Map<String,Object> metadata(long tenant,String id){var rows=jdbc.queryForList("SELECT * FROM ful_private_file WHERE tenant_id=? AND id=?",tenant,id);if(rows.isEmpty())throw exception(FILE_INVALID);return rows.get(0);}
    public Path verified(Map<String,Object> meta)throws Exception {
        Path file=path(text(meta,"storage_key"));if(!Files.isRegularFile(file,LinkOption.NOFOLLOW_LINKS)||Files.size(file)!=number(meta,"byte_size")||!hash(file).equals(text(meta,"sha256")))throw new PermanentFailure("FILE_CHANGED_OR_MISSING");return file;
    }
    private static class LimitedOutput extends FilterOutputStream {
        private final long limit;private long count;
        LimitedOutput(OutputStream output,long limit){super(output);this.limit=limit;}
        private void count(int n){count+=n;if(count>limit)throw new PermanentFailure("FILE_SIZE_LIMIT");}
        @Override public void write(int b)throws IOException{count(1);out.write(b);}
        @Override public void write(byte[] b,int offset,int length)throws IOException{count(length);out.write(b,offset,length);}
    }
}
