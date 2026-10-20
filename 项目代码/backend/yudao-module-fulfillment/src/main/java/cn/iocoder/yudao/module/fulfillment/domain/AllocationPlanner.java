package cn.iocoder.yudao.module.fulfillment.domain;

import java.math.BigDecimal;
import java.util.*;

/** Pure deterministic planner. Shares one remaining balance across repeated product lines. */
public final class AllocationPlanner {
    public enum Strategy { PRIORITY_SPLIT, SINGLE_FIRST }
    public record Demand(long itemId,long productId,BigDecimal quantity) {}
    public record Supply(long productId,long warehouseId,long priority,BigDecimal available) {}
    public record Piece(long itemId,long productId,long warehouseId,BigDecimal quantity) {}
    public record Plan(boolean sufficient,List<Piece> pieces) {}
    private record Key(long product,long warehouse) {}

    public static Plan plan(List<Demand> demands,List<Supply> supplies,Strategy strategy) {
        Objects.requireNonNull(strategy);
        Map<Key,BigDecimal> remaining=new HashMap<>();
        Map<Long,Long> priority=new HashMap<>();
        for(Supply s:supplies) {
            if(s.available()==null || s.available().signum()<0 || remaining.put(new Key(s.productId(),s.warehouseId()),s.available())!=null) throw new IllegalArgumentException("Invalid/duplicate supply");
            Long prior=priority.put(s.warehouseId(),s.priority());
            if(prior!=null && prior!=s.priority()) throw new IllegalArgumentException("Inconsistent warehouse priority");
        }
        List<Long> warehouses=priority.keySet().stream().sorted(Comparator.<Long>comparingLong(priority::get).thenComparingLong(w->w)).toList();
        Set<Long> ids=new HashSet<>();Map<Long,BigDecimal> total=new HashMap<>();
        for(Demand d:demands) {
            if(d.quantity()==null || d.quantity().signum()<=0 || !ids.add(d.itemId())) throw new IllegalArgumentException("Invalid/duplicate demand");
            total.merge(d.productId(),d.quantity(),BigDecimal::add);
        }
        if(strategy==Strategy.SINGLE_FIRST) {
            for(long warehouse:warehouses) {
                if(total.entrySet().stream().allMatch(e->remaining.getOrDefault(new Key(e.getKey(),warehouse),BigDecimal.ZERO).compareTo(e.getValue())>=0)) {
                    warehouses=List.of(warehouse);break;
                }
            }
        }
        List<Piece> pieces=new ArrayList<>();
        for(Demand d:demands.stream().sorted(Comparator.comparingLong(Demand::itemId)).toList()) {
            BigDecimal needed=d.quantity();
            for(long warehouse:warehouses) {
                Key key=new Key(d.productId(),warehouse);
                BigDecimal available=remaining.getOrDefault(key,BigDecimal.ZERO);
                BigDecimal take=needed.min(available);
                if(take.signum()>0) { pieces.add(new Piece(d.itemId(),d.productId(),warehouse,take));remaining.put(key,available.subtract(take));needed=needed.subtract(take); }
                if(needed.signum()==0) break;
            }
            if(needed.signum()>0) return new Plan(false,List.of());
        }
        return new Plan(true,List.copyOf(pieces));
    }
}
