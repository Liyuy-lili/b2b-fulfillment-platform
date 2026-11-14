"""Fresh-schema recovery and concurrency checks against real services."""

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier

import pymysql
import requests

ROOT = Path(__file__).resolve().parents[1]
JAR = ROOT / "backend/yudao-server/target/yudao-server.jar"
ERP_AVAILABLE_STOCK_SHORTAGE = 1030404000
IDEMPOTENCY_KEY_CONFLICT = 1080000005


def eventually(description, probe, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = probe()
            if result:
                return result
        except requests.RequestException:
            pass
        time.sleep(0.4)
    raise RuntimeError(f"Timed out: {description}")


def fetch(connection, sql, params=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


def mysql(env, database=None):
    return pymysql.connect(host="127.0.0.1", port=int(env["DB_PORT"]), user=env["DB_USER"],
                           password=env["DB_PASSWORD"], database=database, autocommit=True)


def initialize(env, logs):
    schema = env["DB_NAME"]
    with mysql(env) as conn:
        # The name is generated here. CREATE fails on collision before any SQL is loaded.
        fetch(conn, f"CREATE DATABASE {schema} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    args = [os.getenv("CI_MYSQL_CLIENT", "mysql"), "--no-defaults", "--host=127.0.0.1",
            f"--port={env['DB_PORT']}", f"--user={env['DB_USER']}", "--default-character-set=utf8mb4", schema]
    with (logs / "initialize.log").open("wb") as log:
        for path in ("backend/sql/mysql/ruoyi-vue-pro.sql", "deploy/sql/010-erp.sql",
                     "deploy/sql/020-local-baseline.sql"):
            with (ROOT / path).open("rb") as source:
                subprocess.run(args, stdin=source, stdout=log, stderr=subprocess.STDOUT,
                               env={**env, "MYSQL_PWD": env["DB_PASSWORD"]}, check=True, timeout=120)
    with (logs / "migration.log").open("wb") as log:
        subprocess.run(["java", "-Dloader.main=cn.iocoder.yudao.module.fulfillment.framework.FulfillmentMigrationTool",
                        "-cp", str(JAR), "org.springframework.boot.loader.launch.PropertiesLauncher", "baseline"],
                       stdout=log, stderr=subprocess.STDOUT, env=env, check=True, timeout=120)


@contextmanager
def app(env, logs, phase, mq_port, args):
    cmd = ["java", "-Xms128m", "-Xmx768m", "-Dfile.encoding=UTF-8", "-Duser.timezone=Asia/Shanghai",
           "-jar", str(JAR), "--spring.profiles.active=fulfillment,fulfillment-observability",
           "--fulfillment.messages.enabled=true", "--fulfillment.messages.max-attempts=10",
           "--fulfillment.messages.retry-base-ms=1500", "--fulfillment.messages.delay-ms=500",
           "--fulfillment.messages.initial-delay-ms=1000", "--fulfillment.expiry.enabled=false",
           "--fulfillment.jobs.enabled=false", "--fulfillment.observability.sample-delay-ms=750",
           "--fulfillment.observability.initial-delay-ms=500", f"--fulfillment.messages.port={mq_port}",
           f"--spring.data.redis.database={args.redis_db}", f"--server.port={args.app_port}",
           f"--management.server.port={args.management_port}", f"--logging.file.name={logs / (phase + '-app.log')}"]
    with (logs / f"{phase}-console.log").open("wb") as log:
        process = subprocess.Popen(cmd, env=env, cwd=logs, stdout=log, stderr=subprocess.STDOUT)
        try:
            with requests.Session() as session:
                session.headers["tenant-id"] = "1"

                def login():
                    if process.poll() is not None:
                        raise RuntimeError(f"{phase} JVM exited: {process.returncode}")
                    return api(session, args.app_port, "POST", "/system/auth/login",
                               {"username": "admin", "password": "admin123"})

                token = eventually(f"{phase} login", login, 150)
                session.headers["Authorization"] = "Bearer " + token["accessToken"]
                yield session
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)


def api_result(session, port, method, path, body=None, params=None, key=None):
    response = session.request(method, f"http://127.0.0.1:{port}/admin-api{path}", json=body, params=params,
                               headers={"Idempotency-Key": key} if key else None, timeout=10)
    response.raise_for_status()
    return response.json()


def api(session, port, method, path, body=None, params=None, key=None):
    payload = api_result(session, port, method, path, body, params, key)
    if payload["code"] != 0:
        raise RuntimeError(f"{method} {path}: {payload['code']} {payload.get('msg')}")
    return payload["data"]


def prepare_stock(session, port, label):
    def create(resource, body):
        return api(session, port, "POST", f"/erp/{resource}/create", body)

    def approve(resource, record):
        api(session, port, "PUT", f"/erp/{resource}/update-status", params={"id": record, "status": 20})

    now = datetime.now().isoformat(timespec="seconds")
    master = {"name": label, "sort": 1, "status": 0}
    unit = create("product-unit", master)
    category = create("product-category", {**master, "code": label, "parentId": 0})
    supplier = create("supplier", master)
    customer = create("customer", master)
    account = create("account", {**master, "no": label})
    warehouse = create("warehouse", {**master, "warehousePrice": "0", "truckagePrice": "0"})
    product = create("product", {**master, "barCode": label, "unitId": unit,
                                 "categoryId": category, "salePrice": "0"})
    inbound = create("stock-in", {"supplierId": supplier, "inTime": now, "items": [
        {"productId": product, "warehouseId": warehouse, "count": "6", "productPrice": "0"}]})
    approve("stock-in", inbound)
    return product, warehouse, customer, account


def bind_order(session, port, fixture, key):
    product, _, customer, account = fixture
    now = datetime.now().isoformat(timespec="seconds")
    source = api(session, port, "POST", "/erp/sale-order/create",
                 {"customerId": customer, "accountId": account, "orderTime": now, "items": [
        {"productId": product, "count": "4", "productPrice": "0", "taxPercent": "0"}]})
    api(session, port, "PUT", "/erp/sale-order/update-status", params={"id": source, "status": 20})
    return api(session, port, "POST", "/fulfillment/order/bind", {"erpOrderId": str(source)}, key=key)["orderId"]


def allocation_request(order, warehouse):
    return {"orderId": order, "warehouseIds": [str(warehouse)], "strategy": "PRIORITY_SPLIT", "holdSeconds": 900}


def race(session, first, second):
    gate = Barrier(2, timeout=5)

    def run_request(request):
        with requests.Session() as client:
            client.headers.update(session.headers)
            gate.wait()
            return request(client)

    with ThreadPoolExecutor(max_workers=2) as pool:
        return tuple(pool.map(run_request, (first, second)))


def metrics(port):
    response = requests.get(f"http://127.0.0.1:{port}/actuator/prometheus", timeout=5)
    response.raise_for_status()
    samples = {}
    for line in response.text.splitlines():
        if not line.startswith("fulfillment_queue_"):
            continue
        series, value = line.rsplit(None, 1)
        name, _, tags = series.partition("{")
        labels = dict(re.findall(r'(\w+)="([^"]*)"', tags))
        samples[name, labels.get("queue"), labels.get("status")] = float(value)
    return samples


def read_state(connection, product, warehouse, order):
    stock = fetch(connection, "SELECT `count`,ful_reserved_count FROM erp_stock "
                  "WHERE product_id=%s AND warehouse_id=%s", (product, warehouse))[0]
    held = fetch(connection, "SELECT COALESCE(SUM(held_qty),0) FROM ful_reservation WHERE order_id=%s", (order,))
    ledger = fetch(connection, "SELECT COALESCE(SUM(held_delta),0) FROM ful_stock_ledger "
                   "WHERE product_id=%s AND warehouse_id=%s", (product, warehouse))
    # Preserve the decimal quantities so fractional corruption cannot be hidden by rounding.
    return tuple(float(value) for value in (*stock, held[0][0], ledger[0][0]))


def check_stock_contention(session, port, conn, check):
    fixture = prepare_stock(session, port, "CI_ORDERS")
    product, warehouse, _, _ = fixture
    first_order = bind_order(session, port, fixture, "ci-orders-bind-first")
    second_order = bind_order(session, port, fixture, "ci-orders-bind-second")

    def allocate(client, order, key):
        return api(client, port, "POST", "/fulfillment/order/allocate",
                   allocation_request(order, warehouse), key=key)

    first, second = race(session,
                         lambda client: allocate(client, first_order, "ci-orders-first"),
                         lambda client: allocate(client, second_order, "ci-orders-second"))
    check("two orders racing for six units yield one reservation and one shortage",
          sorted((result["outcome"], result["status"]) for result in (first, second)),
          [("ALLOCATED", "RESERVED"), ("INSUFFICIENT_STOCK", "WAIT_STOCK")])
    winner, loser = sorted((first, second), key=lambda result: result["outcome"])
    check("order race commits matching stock, per-order holds and ledger",
          [read_state(conn, product, warehouse, result["orderId"]) for result in (winner, loser)],
          [(6, 4, 4, 4), (6, 4, 0, 4)])
    item_id = winner["reservations"][0]["orderItemId"]
    canceled = api(session, port, "POST", "/fulfillment/order/cancel", {
        "orderId": winner["orderId"], "items": [{"id": item_id, "quantity": "4"}], "reason": "CI race cleanup"
    }, key="ci-orders-cancel")
    check("cancel releases the winning hold without reducing physical stock",
          (canceled["orderStatus"], read_state(conn, product, warehouse, winner["orderId"])),
          ("CANCELLED", (6, 0, 0, 0)))

    fixture = prepare_stock(session, port, "CI_DUPLICATE")
    product, warehouse, _, _ = fixture
    order = bind_order(session, port, fixture, "ci-duplicate-bind")
    key = "ci-duplicate-allocate"

    def duplicate(client):
        return allocate(client, order, key)

    first, second = race(session, duplicate, duplicate)
    check("concurrent identical commands replay the same successful response",
          (first["outcome"], second), ("ALLOCATED", first))
    altered = {**allocation_request(order, warehouse), "holdSeconds": 901}
    conflict = api_result(session, port, "POST", "/fulfillment/order/allocate", altered, key=key)
    check("same key with a different hold duration returns a conflict", conflict["code"], IDEMPOTENCY_KEY_CONFLICT)
    check("duplicate and conflicting calls leave one command and one reservation event",
          (fetch(conn, "SELECT COUNT(*) FROM ful_command_record WHERE idempotency_key=%s", (key,))[0][0],
           fetch(conn, "SELECT COUNT(*) FROM ful_outbox_event WHERE order_id=%s AND event_type='STOCK_RESERVED'",
                 (order,))[0][0], read_state(conn, product, warehouse, order)),
          (1, 1, (6, 4, 4, 4)))

    fixture = prepare_stock(session, port, "CI_LEGACY")
    product, warehouse, customer, _ = fixture
    order = bind_order(session, port, fixture, "ci-legacy-bind")
    out = api(session, port, "POST", "/erp/stock-out/create", {
        "customerId": customer, "outTime": datetime.now().isoformat(timespec="seconds"), "items": [
            {"productId": product, "warehouseId": warehouse, "count": "4", "productPrice": "0"}]
    })
    allocation, stock_out = race(
        session, lambda client: allocate(client, order, "ci-legacy-allocate"),
        lambda client: api_result(client, port, "PUT", "/erp/stock-out/update-status",
                                  params={"id": out, "status": 20}))
    out_status = api(session, port, "GET", "/erp/stock-out/get", params={"id": out})["status"]
    stock_records = fetch(conn, "SELECT COUNT(*) FROM erp_stock_record WHERE product_id=%s AND warehouse_id=%s",
                          (product, warehouse))[0][0]
    # Either request may win. Verify its committed effects and the losing transaction's lack of side effects.
    outcomes = {
        "ALLOCATED": ("RESERVED", ERP_AVAILABLE_STOCK_SHORTAGE, 10, 1, (6, 4, 4, 4)),
        "INSUFFICIENT_STOCK": ("WAIT_STOCK", 0, 20, 2, (2, 0, 0, 0)),
    }
    check("legacy stock-out and reservation serialize and preserve both ledgers",
          (allocation["status"], stock_out["code"], out_status, stock_records,
           read_state(conn, product, warehouse, order)),
          outcomes[allocation["outcome"]])


def run(args, logs, report):
    schema = "fulfillment_ci_" + uuid.uuid4().hex[:12]
    env = {**os.environ, "DB_NAME": schema, "DB_HOST": "127.0.0.1", "REDIS_HOST": "127.0.0.1",
           "MQ_HOST": "127.0.0.1", "DB_PORT": str(args.mysql_port), "REDIS_PORT": str(args.redis_port),
           "DB_USER": os.getenv("CI_MYSQL_USER", "root"), "DB_PASSWORD": os.environ["CI_MYSQL_PASSWORD"],
           "MQ_USER": os.environ["CI_MQ_USER"], "MQ_PASSWORD": os.environ["CI_MQ_PASSWORD"],
           "MQ_VHOST": os.environ["CI_MQ_VHOST"], "FULFILLMENT_FILE_ROOT": str(logs / "private-files")}
    report["schema"] = schema
    with JAR.open("rb") as jar:
        report["jar_sha256"] = hashlib.file_digest(jar, "sha256").hexdigest()

    def check(name, actual, expected):
        passed = actual == expected
        report["checks"].append({"name": name, "passed": passed, "actual": actual, "expected": expected})
        print(("PASS " if passed else "FAIL ") + name, flush=True)
        if not passed:
            raise AssertionError(f"{name}: {actual!r} != {expected!r}")

    def pending(samples, queue, states):
        return sum(samples.get(("fulfillment_queue_records", queue, state), float("nan")) for state in states)

    success_key = ("fulfillment_queue_sample_success", None, None)
    timestamp_key = ("fulfillment_queue_sample_last_success_timestamp_seconds", None, None)
    outbox_states = ("NEW", "RETRY_WAIT", "IN_FLIGHT")
    inbox_states = ("NEW", "RETRY_WAIT")
    file_states = ("PENDING", "RETRY_WAIT", "RUNNING", "CANCEL_REQUESTED")

    def capture(probe, description):
        def sample():
            samples = metrics(args.management_port)
            return samples if probe(samples) else None
        return eventually(description, sample)

    initialize(env, logs)
    # Hold a bound, non-listening port for this phase to guarantee connection failure
    # without stopping the shared service or relying on a hard-coded unused port.
    with mysql(env, schema) as conn, socket.socket() as unreachable:
        unreachable.bind(("127.0.0.1", 0))
        report["transport_fault"] = "application pointed at a bound, non-listening loopback TCP port"
        with app(env, logs, "unavailable", unreachable.getsockname()[1], args) as session:
            check("V1 to V8 applied", tuple(int(row[0]) for row in fetch(conn,
                  "SELECT version FROM ful_flyway_schema_history WHERE type='SQL' ORDER BY installed_rank")),
                  tuple(range(1, 9)))
            empty = capture(lambda s: s.get(success_key) == 1, "first successful database sample")
            check("empty job queue sampled", pending(empty, "file_job", file_states), 0)
            app_endpoint = requests.get(f"http://127.0.0.1:{args.app_port}/actuator/prometheus", timeout=5)
            check("Prometheus unavailable on the application listener",
                  "fulfillment_queue_sample_success" in app_endpoint.text, False)
            fixture = prepare_stock(session, args.app_port, "CI_RECOVERY")
            product, warehouse, _, _ = fixture
            order = bind_order(session, args.app_port, fixture, "ci-bind")
            request = allocation_request(order, warehouse)
            allocated = api(session, args.app_port, "POST", "/fulfillment/order/allocate", request, key="ci-allocate")
            check("allocated with transport unavailable", allocated["outcome"], "ALLOCATED")
            check("H, R, active reservations and ledger after allocation",
                  read_state(conn, product, warehouse, order), (6, 4, 4, 4))
            event_count = fetch(conn, "SELECT COUNT(*) FROM ful_outbox_event WHERE order_id=%s", (order,))[0][0]
            check("binding and allocation emitted two events", event_count, 2)
            backlog = capture(lambda s: s.get(success_key) == 1
                              and s.get(("fulfillment_queue_records", "outbox", "RETRY_WAIT")) == event_count
                              and s.get(("fulfillment_queue_oldest_pending_seconds", "outbox", None), 0) >= 1,
                              "observed retry backlog and age")
            check("all events visible in retry backlog", pending(backlog, "outbox", outbox_states), event_count)
            oldest_age = fetch(conn, "SELECT TIMESTAMPDIFF(SECOND,MIN(created_at),UTC_TIMESTAMP(6)) "
                               "FROM ful_outbox_event")[0][0]
            sampled_age = backlog[("fulfillment_queue_oldest_pending_seconds", "outbox", None)]
            check("oldest age agrees with the database UTC clock", abs(oldest_age - sampled_age) <= 5, True)
            check("no fake consumer progress", fetch(conn, "SELECT COUNT(*) FROM ful_inbox_event")[0][0], 0)

            # A MySQL table lock blocks one of the three sample queries without modifying business rows.
            with mysql(env, schema) as locker:
                fetch(locker, "LOCK TABLES ful_file_job WRITE")
                try:
                    stale = capture(lambda s: s.get(success_key) == 0 and s.get(timestamp_key, 0) > 0,
                                    "sample fails under MySQL lock")
                    check("failed sampler preserves the last good backlog",
                          pending(stale, "outbox", outbox_states), event_count)
                finally:
                    fetch(locker, "UNLOCK TABLES")
            capture(lambda s: s.get(success_key) == 1 and s.get(timestamp_key, 0) > stale[timestamp_key],
                    "sample refreshes after MySQL unlock")
            check("sampler recovers after MySQL unlock", True, True)

        with app(env, logs, "restored", args.mq_port, args) as session:
            sent = eventually("outbox and inbox drain", lambda:
                              fetch(conn, "SELECT COUNT(*) FROM ful_outbox_event WHERE status='SENT'")[0][0] == event_count
                              and fetch(conn, "SELECT COUNT(*) FROM ful_inbox_event WHERE status='PROCESSED'")[0][0] == event_count)
            check("durable outbox and inbox converge", sent, True)
            cleared = capture(lambda s: s.get(success_key) == 1 and pending(s, "outbox", outbox_states) == 0
                              and pending(s, "inbox", inbox_states) == 0, "backlog metrics clear")
            check("pending age resets after drain", cleared[("fulfillment_queue_oldest_pending_seconds", "outbox", None)], 0)
            check("no dead events", (cleared[("fulfillment_queue_records", "outbox", "DEAD")],
                                     cleared[("fulfillment_queue_records", "inbox", "DEAD")]), (0, 0))
            model = fetch(conn, "SELECT observed_version FROM ful_order_read_model WHERE order_id=%s", (order,))
            version = fetch(conn, "SELECT MAX(aggregate_version) FROM ful_outbox_event WHERE order_id=%s", (order,))
            check("read model reaches latest event version", model, version)
            replay = api(session, args.app_port, "POST", "/fulfillment/order/allocate", request, key="ci-allocate")
            check("same command returns the original allocation", replay, allocated)
            check("replay creates no extra event", fetch(conn, "SELECT COUNT(*) FROM ful_outbox_event")[0][0], event_count)
            check("H and R remain correct after recovery and replay",
                  read_state(conn, product, warehouse, order), (6, 4, 4, 4))
            check_stock_contention(session, args.app_port, conn, check)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mysql-port", type=int, required=True)
    parser.add_argument("--redis-port", type=int, required=True)
    parser.add_argument("--mq-port", type=int, required=True)
    parser.add_argument("--redis-db", type=int, default=15, choices=range(1, 16))
    parser.add_argument("--app-port", type=int, default=48108)
    parser.add_argument("--management-port", type=int, default=48109)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for port in (args.app_port, args.management_port):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    args.output = args.output.resolve()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    logs = args.output.parent / (args.output.stem + "-" + uuid.uuid4().hex[:8] + "-logs")
    logs.mkdir()
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "result": "failed", "checks": []}
    try:
        run(args, logs, report)
        report["result"] = "passed"
    except Exception as error:
        report["failure_type"] = type(error).__name__
        raise
    finally:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Report: {args.output}\nLogs: {logs}", flush=True)


if __name__ == "__main__":
    main()
