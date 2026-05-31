import time
import json
import random
import requests
import threading
import uuid
import argparse
import queue
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict

from cluster.runtime.models import StreamKey
from cluster.runtime.events.cluster_event import ClusterEvent

DEFAULT_NODES = [
    "http://100.100.1.200:7000",
    "http://100.100.1.202:7000",
    "http://100.100.1.203:7000",
]

DEFAULT_EVENTS = 100000
DEFAULT_EVENT_DELAY_MIN = 0.1
DEFAULT_EVENT_DELAY_MAX = 0.2
DEFAULT_KILL_PROBABILITY = 0.05
DEFAULT_DEATH_TIME_MIN = 1.5
DEFAULT_DEATH_TIME_MAX = 15.0
DEFAULT_REQUEST_TIMEOUT = 5.0
DEFAULT_MAX_RETRIES = 25
DEFAULT_SLOW_EVENT_THRESHOLD_MS = 500.0
DEFAULT_SLEEP_ONLY_NODE = None
DEFAULT_SEND_WORKERS = 4
DEFAULT_RETRY_BACKOFF_BASE = 0.5
DEFAULT_RETRY_BACKOFF_MAX = 3.0
DEFAULT_TENANT_ID = "chaos"
DEFAULT_APP_ID = "chaos_v4"
DEFAULT_DATA_TYPE = "event"
DEFAULT_SCHEMA_VERSION = "0.1"


def parse_args():
    parser = argparse.ArgumentParser(description="Universal chaos torture runner v4")
    parser.add_argument("--nodes", nargs="+", default=DEFAULT_NODES, help="Node base URLs")
    parser.add_argument("--events", type=int, default=DEFAULT_EVENTS, help="Number of events")
    parser.add_argument("--delay-min", type=float, default=DEFAULT_EVENT_DELAY_MIN, help="Min delay between events")
    parser.add_argument("--delay-max", type=float, default=DEFAULT_EVENT_DELAY_MAX, help="Max delay between events")
    parser.add_argument("--kill-prob", type=float, default=DEFAULT_KILL_PROBABILITY, help="Probability of kill per event")
    parser.add_argument("--death-min", type=float, default=DEFAULT_DEATH_TIME_MIN, help="Min isolation time")
    parser.add_argument("--death-max", type=float, default=DEFAULT_DEATH_TIME_MAX, help="Max isolation time")
    parser.add_argument("--timeout", type=float, default=DEFAULT_REQUEST_TIMEOUT, help="HTTP request timeout")
    parser.add_argument("--retries", type=int, default=DEFAULT_MAX_RETRIES, help="Max retries per event")
    parser.add_argument("--sleep-only-node", default=DEFAULT_SLEEP_ONLY_NODE, help="Always kill the same node")
    parser.add_argument("--slow-ms", type=float, default=DEFAULT_SLOW_EVENT_THRESHOLD_MS, help="Slow event threshold in ms")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    parser.add_argument("--output", default=None, help="Optional explicit output JSON filename")
    parser.add_argument("--send-workers", type=int, default=DEFAULT_SEND_WORKERS, help="Concurrent sender workers")
    parser.add_argument("--retry-backoff-base", type=float, default=DEFAULT_RETRY_BACKOFF_BASE, help="Base retry backoff seconds")
    parser.add_argument("--retry-backoff-max", type=float, default=DEFAULT_RETRY_BACKOFF_MAX, help="Max retry backoff seconds")
    parser.add_argument("--drain-timeout", type=float, default=60.0, help="Seconds to wait for queue drain after producer ends")
    parser.add_argument("--tenant-id", default=DEFAULT_TENANT_ID, help="Stream tenant id")
    parser.add_argument("--app-id", default=DEFAULT_APP_ID, help="Stream app id")
    parser.add_argument("--data-type", default=DEFAULT_DATA_TYPE, help="Stream data type")
    parser.add_argument("--schema-version", default=DEFAULT_SCHEMA_VERSION, help="Stream schema version")
    return parser.parse_args()


ARGS = parse_args()

if ARGS.seed is not None:
    random.seed(ARGS.seed)

NODES = ARGS.nodes
EVENTS = ARGS.events
EVENT_DELAY_RANGE = (ARGS.delay_min, ARGS.delay_max)
KILL_PROBABILITY = ARGS.kill_prob
DEATH_TIME_RANGE = (ARGS.death_min, ARGS.death_max)
REQUEST_TIMEOUT = ARGS.timeout
MAX_RETRIES = ARGS.retries
SLEEP_ONLY_NODE = ARGS.sleep_only_node
SLOW_EVENT_THRESHOLD_MS = ARGS.slow_ms
SEND_WORKERS = ARGS.send_workers
RETRY_BACKOFF_BASE = ARGS.retry_backoff_base
RETRY_BACKOFF_MAX = ARGS.retry_backoff_max
DRAIN_TIMEOUT = ARGS.drain_timeout
STREAM_KEY = StreamKey(
    tenant_id=ARGS.tenant_id,
    app_id=ARGS.app_id,
    data_type=ARGS.data_type,
    schema_version=ARGS.schema_version,
)

TEST_STARTED_AT = time.time()
RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
STATS_FILE = ARGS.output or f"chaos_stats_{RUN_ID}.json"

TEST_CONFIG = {
    "nodes": NODES,
    "events": EVENTS,
    "event_delay_range": EVENT_DELAY_RANGE,
    "kill_probability": KILL_PROBABILITY,
    "death_time_range": DEATH_TIME_RANGE,
    "request_timeout": REQUEST_TIMEOUT,
    "max_retries": MAX_RETRIES,
    "sleep_only_node": SLEEP_ONLY_NODE,
    "slow_event_threshold_ms": SLOW_EVENT_THRESHOLD_MS,
    "seed": ARGS.seed,
    "run_id": RUN_ID,
    "stats_file": STATS_FILE,
    "send_workers": SEND_WORKERS,
    "retry_backoff_base": RETRY_BACKOFF_BASE,
    "retry_backoff_max": RETRY_BACKOFF_MAX,
    "drain_timeout": DRAIN_TIMEOUT,
    "stream": {
        "tenant_id": STREAM_KEY.tenant_id,
        "app_id": STREAM_KEY.app_id,
        "data_type": STREAM_KEY.data_type,
        "schema_version": STREAM_KEY.schema_version,
        "stream_id": STREAM_KEY.stream_id(),
    },
}

kill_threads = []
dead_nodes = set()

dead_lock = threading.Lock()
stats_lock = threading.Lock()
producer_done_lock = threading.Lock()
enqueue_seq_lock = threading.Lock()

pending_queue = queue.PriorityQueue()
producer_done = False
enqueue_seq = 0

stats = {
    "events_total": 0,
    "events_ok": 0,
    "events_failed": 0,
    "events_retried": 0,
    "events_no_leader": 0,
    "events_timeout": 0,
    "events_connection_error": 0,
    "events_forward_error": 0,
    "events_unexpected_fail": 0,
    "events_slow": 0,
    "kills": 0,
    "revives": 0,
    "kill_attempts": 0,
    "kill_failures": 0,
    "revive_failures": 0,
    "per_node_ok": defaultdict(int),
    "per_node_fail": defaultdict(int),
    "leaders_seen": defaultdict(int),
    "latency": [],
    "unexpected_failures": [],
    "slow_events": [],
    "kill_events": [],
    "submit_http_200": 0,
    "submit_semantic_ok": 0,
    "submit_hard_fail": 0,
    "queue_requeues": 0,
    "queue_max_depth": 0,
}


@dataclass
class PendingEvent:
    event_index: int
    event: dict
    retries_done: int = 0
    tried_nodes: set = field(default_factory=set)
    first_enqueued_at: float = field(default_factory=time.time)


def build_event(i):
    event = ClusterEvent(
        event_type="chaos.test",
        payload={
            "msg": f"msg-203: {i}",
            "seq": i,
            "source": "chaos_v4",
            "run_id": RUN_ID,
            "stream_id": STREAM_KEY.stream_id(),
        },
    )
    return event.model_dump()


def stat_inc(key, amount=1):
    with stats_lock:
        stats[key] += amount


def stat_node_ok(node):
    with stats_lock:
        stats["per_node_ok"][node] += 1


def stat_node_fail(node):
    with stats_lock:
        stats["per_node_fail"][node] += 1


def stat_leader(name):
    with stats_lock:
        stats["leaders_seen"][name] += 1


def stat_latency(ms):
    with stats_lock:
        stats["latency"].append(ms)


def stat_unexpected_failure(event_index, attempt, node, status_code=None, payload=None, reason=None):
    with stats_lock:
        stats["events_unexpected_fail"] += 1
        stats["unexpected_failures"].append({
            "event_index": event_index,
            "attempt": attempt,
            "node": node,
            "status_code": status_code,
            "payload": payload,
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
        })


def stat_slow_event(event_index, attempt, node, latency_ms, leader=None, payload=None):
    with stats_lock:
        stats["events_slow"] += 1
        stats["slow_events"].append({
            "event_index": event_index,
            "attempt": attempt,
            "node": node,
            "latency_ms": round(latency_ms, 3),
            "leader": leader,
            "payload": payload,
            "timestamp": datetime.now().isoformat(),
        })


def stat_kill_event(node, action, ok, payload=None, error=None, seconds=None):
    with stats_lock:
        stats["kill_events"].append({
            "action": action,
            "node": node,
            "ok": ok,
            "seconds": seconds,
            "payload": payload,
            "error": error,
            "timestamp": datetime.now().isoformat(),
        })


def percentile(data, p):
    if not data:
        return 0.0
    values = sorted(data)
    if len(values) == 1:
        return float(values[0])
    rank = (len(values) - 1) * (p / 100.0)
    low = int(rank)
    high = min(low + 1, len(values) - 1)
    fraction = rank - low
    return float(values[low] + (values[high] - values[low]) * fraction)


def is_retryable_response(payload):
    if not isinstance(payload, dict):
        return False
    if payload.get("error") in {"no leader", "node isolated"}:
        return True
    error = str(payload.get("error", "")).lower()
    retry_patterns = ["timeout", "connection", "refused", "temporarily unavailable", "isolated", "no leader"]
    return any(p in error for p in retry_patterns)


def extract_leader(payload):
    if not isinstance(payload, dict):
        return None
    if "result" in payload and isinstance(payload["result"], dict):
        return payload["result"].get("leader")
    return payload.get("leader")


def classify_submit_response(status_code, payload):
    if status_code != 200:
        return "http_not_ok"
    if not isinstance(payload, dict):
        return "submit_ok"
    if payload.get("error"):
        if is_retryable_response(payload):
            return "retryable_error"
        return "hard_fail"
    result = payload.get("result")
    if isinstance(result, dict) and result.get("error"):
        if is_retryable_response(result):
            return "retryable_error"
        return "hard_fail"
    return "submit_ok"


def next_enqueue_seq():
    global enqueue_seq
    with enqueue_seq_lock:
        enqueue_seq += 1
        return enqueue_seq


def enqueue_pending(pending, delay_seconds=0.0):
    run_at = time.time() + max(0.0, delay_seconds)
    pending_queue.put((run_at, next_enqueue_seq(), pending))
    with stats_lock:
        depth = pending_queue.qsize()
        if depth > stats["queue_max_depth"]:
            stats["queue_max_depth"] = depth


def mark_producer_done():
    global producer_done
    with producer_done_lock:
        producer_done = True


def is_producer_done():
    with producer_done_lock:
        return producer_done


def compute_retry_backoff(retries_done):
    backoff = RETRY_BACKOFF_BASE * (2 ** max(0, retries_done - 1))
    return min(backoff, RETRY_BACKOFF_MAX)


def print_test_config():
    print("
" + "=" * 56)
    print("CHAOS TEST CONFIG v4")
    print("=" * 56)
    print(f"run_id..............: {RUN_ID}")
    print(f"stats_file..........: {STATS_FILE}")
    print(f"started_at..........: {datetime.fromtimestamp(TEST_STARTED_AT).isoformat()}")
    print(f"stream_id...........: {STREAM_KEY.stream_id()}")
    print(f"stream_tenant.......: {STREAM_KEY.tenant_id}")
    print(f"stream_app..........: {STREAM_KEY.app_id}")
    print(f"stream_type.........: {STREAM_KEY.data_type}")
    print(f"stream_schema.......: {STREAM_KEY.schema_version}")
    print(f"nodes...............: {NODES}")
    print(f"events..............: {EVENTS}")
    print(f"event_delay_range...: {EVENT_DELAY_RANGE}")
    print(f"kill_probability....: {KILL_PROBABILITY}")
    print(f"death_time_range....: {DEATH_TIME_RANGE}")
    print(f"request_timeout.....: {REQUEST_TIMEOUT}")
    print(f"max_retries.........: {MAX_RETRIES}")
    print(f"sleep_only_node.....: {SLEEP_ONLY_NODE}")
    print(f"slow_threshold_ms...: {SLOW_EVENT_THRESHOLD_MS}")
    print(f"send_workers........: {SEND_WORKERS}")
    print(f"retry_backoff_base..: {RETRY_BACKOFF_BASE}")
    print(f"retry_backoff_max...: {RETRY_BACKOFF_MAX}")
    print(f"drain_timeout.......: {DRAIN_TIMEOUT}")
    print(f"seed................: {ARGS.seed}")
    print("=" * 56 + "
")


def kill_node(node, seconds=None):
    stat_inc("kill_attempts")
    try:
        resp = requests.post(f"{node}/sleep", timeout=2)
        try:
            payload = resp.json()
        except Exception:
            payload = {"raw_text": resp.text}
        if resp.status_code == 200 and payload.get("ok") is True:
            with dead_lock:
                dead_nodes.add(node)
            stat_inc("kills")
            stat_kill_event(node=node, action="sleep", ok=True, payload=payload, seconds=seconds)
            print(f"[CHAOS] SLEEP {node}")
            return True
        stat_inc("kill_failures")
        stat_kill_event(node=node, action="sleep", ok=False, payload=payload, seconds=seconds)
        print(f"[CHAOS FAIL SLEEP] {node} -> status={resp.status_code} payload={payload}")
        return False
    except Exception as e:
        stat_inc("kill_failures")
        stat_kill_event(node=node, action="sleep", ok=False, error=str(e), seconds=seconds)
        print(f"[CHAOS FAIL SLEEP] {node} -> {e}")
        return False


def revive_node(node):
    try:
        resp = requests.post(f"{node}/revive", timeout=2)
        try:
            payload = resp.json()
        except Exception:
            payload = {"raw_text": resp.text}
        if resp.status_code == 200 and payload.get("ok") is True:
            with dead_lock:
                dead_nodes.discard(node)
            stat_inc("revives")
            stat_kill_event(node=node, action="revive", ok=True, payload=payload)
            print(f"[CHAOS] REVIVE {node}")
            return True
        stat_inc("revive_failures")
        stat_kill_event(node=node, action="revive", ok=False, payload=payload)
        print(f"[CHAOS FAIL REVIVE] {node} -> status={resp.status_code} payload={payload}")
        return False
    except Exception as e:
        stat_inc("revive_failures")
        stat_kill_event(node=node, action="revive", ok=False, error=str(e))
        print(f"[CHAOS FAIL REVIVE] {node} -> {e}")
        return False


def kill_cycle(node, seconds):
    try:
        ok = kill_node(node, seconds=seconds)
        if ok:
            print(f"[CHAOS] DEAD {node} for {seconds:.2f}s")
            time.sleep(seconds)
    finally:
        revive_node(node)


def process_pending_event(pending: PendingEvent):
    i = pending.event_index
    event = pending.event
    attempt_number = pending.retries_done + 1
    available = [n for n in NODES if n not in pending.tried_nodes]
    if not available:
        pending.tried_nodes.clear()
        available = list(NODES)
    node = random.choice(available)
    pending.tried_nodes.add(node)
    start = time.time()
    try:
        r = requests.post(f"{node}/event", json=event, timeout=REQUEST_TIMEOUT)
        elapsed_ms = (time.time() - start) * 1000
        stat_latency(elapsed_ms)
        payload = {}
        try:
            payload = r.json()
        except Exception:
            payload = {"raw_text": r.text}
        leader = extract_leader(payload)
        if leader:
            stat_leader(leader)
        if elapsed_ms >= SLOW_EVENT_THRESHOLD_MS:
            stat_slow_event(event_index=i, attempt=attempt_number, node=node, latency_ms=elapsed_ms, leader=leader, payload=payload)
        if r.status_code == 200:
            stat_inc("submit_http_200")
        result = classify_submit_response(r.status_code, payload)
        if result == "submit_ok":
            stat_inc("events_ok")
            stat_inc("submit_semantic_ok")
            stat_node_ok(node)
            print(f"[TORTURE] {i:03} OK attempt={attempt_number} node={node} leader={leader} latency={elapsed_ms:.1f}ms")
            return True
        if result == "retryable_error" or r.status_code >= 500:
            stat_inc("events_retried")
            if isinstance(payload, dict) and payload.get("error") == "no leader":
                stat_inc("events_no_leader")
            result_payload = payload.get("result") if isinstance(payload.get("result"), dict) else None
            if isinstance(result_payload, dict) and result_payload.get("error") == "no leader":
                stat_inc("events_no_leader")
            print(f"[RETRY] {i:03} attempt={attempt_number} node={node} status={r.status_code} payload={payload}")
            if pending.retries_done + 1 >= MAX_RETRIES:
                stat_inc("events_failed")
                stat_unexpected_failure(event_index=i, attempt=attempt_number, node=node, status_code=r.status_code, payload=payload, reason="dropped_after_retries_retryable_response")
                print(f"[DROP] {i:03} event dropped after retries")
                return False
            pending.retries_done += 1
            stat_inc("queue_requeues")
            enqueue_pending(pending, compute_retry_backoff(pending.retries_done))
            return False
        stat_inc("events_failed")
        stat_inc("submit_hard_fail")
        stat_node_fail(node)
        stat_unexpected_failure(event_index=i, attempt=attempt_number, node=node, status_code=r.status_code, payload=payload, reason="hard_fail_non_retryable_response")
        print(f"[FAIL] {i:03} attempt={attempt_number} node={node} status={r.status_code} payload={payload}")
        return False
    except requests.Timeout as e:
        stat_inc("events_timeout")
        stat_inc("events_retried")
        print(f"[TIMEOUT] {i:03} attempt={attempt_number} {node} -> {e}")
    except requests.ConnectionError as e:
        stat_inc("events_connection_error")
        stat_inc("events_retried")
        print(f"[CONNECTION] {i:03} attempt={attempt_number} {node} -> {e}")
    except Exception as e:
        stat_inc("events_forward_error")
        stat_inc("events_retried")
        stat_unexpected_failure(event_index=i, attempt=attempt_number, node=node, reason=f"exception:{type(e).__name__}", payload={"exception": str(e)})
        print(f"[ERROR] {i:03} attempt={attempt_number} {node} -> {e}")
    if pending.retries_done + 1 >= MAX_RETRIES:
        stat_inc("events_failed")
        stat_unexpected_failure(event_index=i, attempt=attempt_number, node=node, reason="dropped_after_retries_exception", payload={"tried_nodes": list(pending.tried_nodes)})
        print(f"[DROP] {i:03} event dropped after retries")
        return False
    pending.retries_done += 1
    stat_inc("queue_requeues")
    enqueue_pending(pending, compute_retry_backoff(pending.retries_done))
    return False


def sender_worker(worker_id):
    while True:
        try:
            run_at, _, pending = pending_queue.get(timeout=0.5)
        except queue.Empty:
            if is_producer_done() and pending_queue.empty():
                return
            continue
        now = time.time()
        if run_at > now:
            pending_queue.put((run_at, next_enqueue_seq(), pending))
            pending_queue.task_done()
            time.sleep(min(run_at - now, 0.2))
            continue
        try:
            process_pending_event(pending)
        finally:
            pending_queue.task_done()


def chaos_loop():
    for i in range(EVENTS):
        if random.random() < KILL_PROBABILITY:
            node = SLEEP_ONLY_NODE if SLEEP_ONLY_NODE else random.choice(NODES)
            seconds = random.uniform(*DEATH_TIME_RANGE)
            t = threading.Thread(target=kill_cycle, args=(node, seconds), daemon=True)
            t.start()
            kill_threads.append(t)
        stat_inc("events_total")
        pending = PendingEvent(event_index=i, event=build_event(i))
        enqueue_pending(pending, delay_seconds=0.0)
        time.sleep(random.uniform(*EVENT_DELAY_RANGE))
    mark_producer_done()


def revive_everything():
    print("
[MAIN] REVIVING ALL NODES
")
    unique_nodes = sorted(set(NODES))
    for node in unique_nodes:
        try:
            requests.post(f"{node}/revive", timeout=2)
            print(f"[FORCE REVIVE] {node}")
        except Exception as e:
            print(f"[FORCE REVIVE FAIL] {node} -> {e}")


def wait_kills():
    print("
[MAIN] waiting active kill cycles...
")
    for t in kill_threads:
        t.join(timeout=30)


def wait_queue_drain():
    deadline = time.time() + DRAIN_TIMEOUT
    while time.time() < deadline:
        if pending_queue.empty():
            time.sleep(0.5)
            if pending_queue.empty():
                return True
        time.sleep(0.2)
    return False


def print_stats():
    ended_at = time.time()
    print("
")
    print("=" * 56)
    print("FINAL CHAOS STATS v4")
    print("=" * 56)
    with stats_lock:
        total = stats["events_total"]
        ok = stats["events_ok"]
        failed = stats["events_failed"]
        success_rate = ((ok / total) * 100) if total else 0
        avg_latency = (sum(stats["latency"]) / len(stats["latency"])) if stats["latency"] else 0
        max_latency = max(stats["latency"]) if stats["latency"] else 0
        min_latency = min(stats["latency"]) if stats["latency"] else 0
        p50_latency = percentile(stats["latency"], 50)
        p95_latency = percentile(stats["latency"], 95)
        p99_latency = percentile(stats["latency"], 99)
        print(f"events_total........: {total}")
        print(f"events_ok...........: {ok}")
        print(f"events_failed.......: {failed}")
        print(f"success_rate........: {success_rate:.2f}%")
        print()
        print(f"events_retried......: {stats['events_retried']}")
        print(f"events_no_leader....: {stats['events_no_leader']}")
        print(f"timeouts............: {stats['events_timeout']}")
        print(f"connection_errors...: {stats['events_connection_error']}")
        print(f"forward_errors......: {stats['events_forward_error']}")
        print(f"unexpected_fail.....: {stats['events_unexpected_fail']}")
        print(f"slow_events.........: {stats['events_slow']}")
        print()
        print(f"submit_http_200.....: {stats['submit_http_200']}")
        print(f"submit_semantic_ok..: {stats['submit_semantic_ok']}")
        print(f"submit_hard_fail....: {stats['submit_hard_fail']}")
        print(f"queue_requeues......: {stats['queue_requeues']}")
        print(f"queue_max_depth.....: {stats['queue_max_depth']}")
        print()
        print(f"kill_attempts.......: {stats['kill_attempts']}")
        print(f"kills...............: {stats['kills']}")
        print(f"kill_failures.......: {stats['kill_failures']}")
        print(f"revives.............: {stats['revives']}")
        print(f"revive_failures.....: {stats['revive_failures']}")
        print()
        print(f"latency_avg.........: {avg_latency:.1f} ms")
        print(f"latency_min.........: {min_latency:.1f} ms")
        print(f"latency_p50.........: {p50_latency:.1f} ms")
        print(f"latency_p95.........: {p95_latency:.1f} ms")
        print(f"latency_p99.........: {p99_latency:.1f} ms")
        print(f"latency_max.........: {max_latency:.1f} ms")
        print()
        print("LEADERS SEEN")
        for leader, count in sorted(stats["leaders_seen"].items()):
            print(f"  {leader:15} -> {count}")
        print()
        print("NODE SUCCESS")
        for node, count in sorted(stats["per_node_ok"].items()):
            print(f"  {node:30} -> {count}")
        print()
        print("NODE FAIL")
        for node, count in sorted(stats["per_node_fail"].items()):
            print(f"  {node:30} -> {count}")
        print()
        print("SLOW EVENTS")
        if stats["slow_events"]:
            for idx, item in enumerate(stats["slow_events"][:20], start=1):
                print(f"  #{idx:02} event={item.get('event_index')} attempt={item.get('attempt')} node={item.get('node')} leader={item.get('leader')} latency_ms={item.get('latency_ms')}")
            if len(stats["slow_events"]) > 20:
                print(f"  ... and {len(stats['slow_events']) - 20} more")
        else:
            print("  none")
        print()
        print("UNEXPECTED FAILURES")
        if stats["unexpected_failures"]:
            for idx, item in enumerate(stats["unexpected_failures"][:20], start=1):
                print(f"  #{idx:02} event={item.get('event_index')} attempt={item.get('attempt')} node={item.get('node')} status={item.get('status_code')} reason={item.get('reason')}")
            if len(stats["unexpected_failures"]) > 20:
                print(f"  ... and {len(stats['unexpected_failures']) - 20} more")
        else:
            print("  none")
        print("=" * 56)
        report = {
            "test_config": TEST_CONFIG,
            "run_meta": {
                "started_at_epoch": TEST_STARTED_AT,
                "ended_at_epoch": ended_at,
                "started_at_iso": datetime.fromtimestamp(TEST_STARTED_AT).isoformat(),
                "ended_at_iso": datetime.fromtimestamp(ended_at).isoformat(),
                "duration_seconds": round(ended_at - TEST_STARTED_AT, 3),
            },
            "stats": {
                **stats,
                "success_rate": round(success_rate, 2),
                "latency_avg": round(avg_latency, 3),
                "latency_min": round(min_latency, 3),
                "latency_p50": round(p50_latency, 3),
                "latency_p95": round(p95_latency, 3),
                "latency_p99": round(p99_latency, 3),
                "latency_max": round(max_latency, 3),
                "per_node_ok": dict(stats["per_node_ok"]),
                "per_node_fail": dict(stats["per_node_fail"]),
                "leaders_seen": dict(stats["leaders_seen"]),
            }
        }
        with open(STATS_FILE, "w") as f:
            json.dump(report, f, indent=2)
        print(f"
[MAIN] stats saved to {STATS_FILE}
")


def main():
    print("[MAIN] starting UNIVERSAL chaos torture v4")
    print_test_config()
    workers = []
    for idx in range(SEND_WORKERS):
        t = threading.Thread(target=sender_worker, args=(idx,), daemon=True)
        t.start()
        workers.append(t)
    drained = False
    try:
        chaos_loop()
        drained = wait_queue_drain()
        pending_queue.join()
        for t in workers:
            t.join(timeout=5)
    finally:
        wait_kills()
        revive_everything()
        if not drained:
            print(f"
[MAIN WARN] queue drain timeout reached after {DRAIN_TIMEOUT:.1f}s
")
        print_test_config()
        print_stats()
        print("
[MAIN] cluster restored
")


if __name__ == "__main__":
    main()
