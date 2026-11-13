package cn.iocoder.yudao.module.fulfillment.framework;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

import javax.sql.DataSource;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;
import java.util.stream.Collectors;
import java.util.stream.Stream;

@Configuration(proxyBeanMethods = false)
@EnableScheduling
@Profile("fulfillment-observability")
public class FulfillmentQueueMetrics {

    private static final Logger LOG = LoggerFactory.getLogger(FulfillmentQueueMetrics.class);
    private static final List<Queue> QUEUES = List.of(
            new Queue("outbox", "ful_outbox_event", List.of("NEW", "RETRY_WAIT", "IN_FLIGHT"), List.of("DEAD")),
            new Queue("inbox", "ful_inbox_event", List.of("NEW", "RETRY_WAIT"), List.of("DEAD")),
            new Queue("file_job", "ful_file_job", List.of("PENDING", "RETRY_WAIT", "RUNNING", "CANCEL_REQUESTED"),
                    List.of("FAILED", "PARTIAL_FAILED")));

    private final JdbcTemplate jdbc;
    private final AtomicReference<Snapshot> current =
            new AtomicReference<>(new Snapshot(Map.of(), Map.of(), 0, false));

    public FulfillmentQueueMetrics(DataSource dataSource, MeterRegistry registry) {
        jdbc = new JdbcTemplate(dataSource);
        jdbc.setQueryTimeout(3);
        for (Queue queue : QUEUES) {
            for (String status : queue.statuses()) {
                State state = new State(queue.name(), status);
                Gauge.builder("fulfillment.queue.records", current, ref -> {
                            Snapshot sample = ref.get();
                            return value(sample, sample.counts().get(state));
                        })
                        .description("Records in a tracked fulfillment queue state")
                        .tags("queue", queue.name(), "status", status).register(registry);
            }
            Gauge.builder("fulfillment.queue.oldest.pending", current, ref -> {
                        Snapshot sample = ref.get();
                        return value(sample, sample.oldest().get(queue.name()));
                    }).baseUnit("seconds").description("Age of the oldest unfinished record at sample time")
                    .tag("queue", queue.name()).register(registry);
        }
        Gauge.builder("fulfillment.queue.sample.success", current, ref -> ref.get().success() ? 1 : 0)
                .description("Whether the most recent queue sample succeeded").register(registry);
        Gauge.builder("fulfillment.queue.sample.last.success.timestamp", current, ref -> ref.get().lastSuccess())
                .baseUnit("seconds").description("Unix time of the last successful queue sample").register(registry);
    }

    @Bean
    ThreadPoolTaskScheduler fulfillmentMetricsScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setThreadNamePrefix("ful-metrics-");
        scheduler.setPoolSize(1);
        return scheduler;
    }

    @Scheduled(scheduler = "fulfillmentMetricsScheduler",
            fixedDelayString = "${fulfillment.observability.sample-delay-ms:15000}",
            initialDelayString = "${fulfillment.observability.initial-delay-ms:5000}")
    void sample() {
        Map<State, Long> counts = new HashMap<>();
        Map<String, Long> oldest = new HashMap<>();
        try {
            for (Queue queue : QUEUES) {
                String parameters = queue.statuses().stream().map(status -> "?").collect(Collectors.joining(","));
                String sql = "SELECT status, COUNT(*) AS records, "
                        + "GREATEST(0, TIMESTAMPDIFF(SECOND, MIN(created_at), UTC_TIMESTAMP(6))) AS age "
                        + "FROM " + queue.table() + " WHERE status IN (" + parameters + ") GROUP BY status";
                jdbc.query(sql, rs -> {
                    String status = rs.getString("status");
                    counts.put(new State(queue.name(), status), rs.getLong("records"));
                    if (queue.pending().contains(status)) {
                        oldest.merge(queue.name(), rs.getLong("age"), Math::max);
                    }
                }, queue.statuses().toArray());
            }
            current.set(new Snapshot(Map.copyOf(counts), Map.copyOf(oldest), Instant.now().getEpochSecond(), true));
        } catch (DataAccessException ex) {
            Snapshot previous = current.getAndUpdate(sample ->
                    new Snapshot(sample.counts(), sample.oldest(), sample.lastSuccess(), false));
            if (previous.success()) {
                LOG.warn("Fulfillment queue sample failed ({})", ex.getClass().getSimpleName());
            }
        }
    }

    private static double value(Snapshot sample, Long value) {
        return sample.lastSuccess() == 0 ? Double.NaN : value == null ? 0 : value;
    }

    private record Queue(String name, String table, List<String> pending, List<String> failures) {
        List<String> statuses() {
            return Stream.concat(pending.stream(), failures.stream()).toList();
        }
    }

    private record State(String queue, String status) {}

    private record Snapshot(Map<State, Long> counts, Map<String, Long> oldest, long lastSuccess, boolean success) {}
}
