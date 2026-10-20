package cn.iocoder.yudao.module.erp.dal.mysql.stock;

/** One tenant-local stock identity. Lock order is independent of allocation preference. */
public record StockKey(long productId, long warehouseId) implements Comparable<StockKey> {
    public StockKey {
        if (productId<=0 || warehouseId<=0) throw new IllegalArgumentException("Positive stock identity required");
    }
    @Override public int compareTo(StockKey other) {
        int product=Long.compare(productId,other.productId);
        return product!=0?product:Long.compare(warehouseId,other.warehouseId);
    }
}
