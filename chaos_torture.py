import time
import json
import random
import requests
import threading
from datetime import datetime
from collections import defaultdict

from cluster.runtime.events.cluster_event import ClusterEvent


# =====================================================
# CONFIG
# =====================================================

NODES = [
    "http://100.100.1.200:7000",  # leader
    "http://100.100.1.202:7000",
    "http://100.100.1.203:7000",
]

EVENTS = 1000
EVENT_DELAY_RANGE = (0.2, 0.5)
KILL_PROBABILITY = 0.15
DEATH_TIME_RANGE = (5, 10)
REQUEST_TIMEOUT = 5
MAX_RETRIES = 10
SLEEP_ONLY_NODE = None
# SLEEP_ONLY_NODE = "http://100.100.1.200:7000"


# =====================================================
# RUN META
# =====================================================

TEST_STARTED_AT = time.time()
RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
STATS_FILE = f"chaos_stats_{RUN_ID}.json"

TEST_CONFIG = {
    "nodes": NODES,
    "events": EVENTS,
    "event_delay_range": EVENT_DELAY_RANGE,
    "kill_probability": KILL_PROBABILITY,
    "death_time_range": DEATH_TIME_RANGE,
    "request_timeout": REQUEST_TIMEOUT,
    "max_retries": MAX_RETRIES,
    "sleep_only_node": SLEEP_ONLY_NODE,
    "run_id": RUN_ID,
    "stats_file": STATS_FILE,
}


# =====================================================
# GLOBALS
# =====================================================

kill_threads = []
dead_nodes = set()

dead_lock = threading.Lock()
stats_lock = threading.Lock()

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
    "kills": 0,
    "revives": 0,
    "per_node_ok": defaultdict(int),
    "per_node_fail": defaultdict(int),
    "leaders_seen": defaultdict(int),
    "latency": [],
    "unexpected_failures": [],
}


# =====================================================
# HELPERS
# =====================================================

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


def is_retryable_response(payload):
    if not isinstance(payload, dict):
        return False

    if payload.get("error") == "no leader":
        return True

    error = str(payload.get("error", "")).lower()

    retry_patterns = [
        "timeout",
        "connection",
        "refused",
        "temporarily unavailable",
    ]

    return any(p in error for p in retry_patterns)


def print_test_config():
    print("\n" + "=" * 60)
    print("CHAOS TEST CONFIG")
    print("=" * 60)
    print(f"run_id..............: {RUN_ID}")
    print(f"stats_file..........: {STATS_FILE}")
    print(f"started_at..........: {datetime.fromtimestamp(TEST_STARTED_AT).isoformat()}")
    print(f"nodes...............: {NODES}")
    print(f"events..............: {EVENTS}")
    print(f"event_delay_range...: {EVENT_DELAY_RANGE}")
    print(f"kill_probability....: {KILL_PROBABILITY}")
    print(f"death_time_range....: {DEATH_TIME_RANGE}")
    print(f"request_timeout.....: {REQUEST_TIMEOUT}")
    print(f"max_retries.........: {MAX_RETRIES}")
    print(f"sleep_only_node.....: {SLEEP_ONLY_NODE}")
    print("=" * 60 + "\n")


# =====================================================
# KILL / REVIVE
# =====================================================

def kill_node(node):
    try:
        requests.post(f"{node}/sleep", timeout=1)

        with dead_lock:
            dead_nodes.add(node)

        stat_inc("kills")
        print(f"[CHAOS] SLEEP {node}")

    except Exception as e:
        print(f"[CHAOS FAIL SLEEP] {node} -> {e}")


def revive_node(node):
    try:
        requests.post(f"{node}/revive", timeout=1)

        with dead_lock:
            dead_nodes.discard(node)

        stat_inc("revives")
        print(f"[CHAOS] REVIVE {node}")

    except Exception as e:
        print(f"[CHAOS FAIL REVIVE] {node} -> {e}")


def kill_cycle(node, seconds):
    try:
        kill_node(node)
        print(f"[CHAOS] DEAD {node} for {seconds:.2f}s")
        time.sleep(seconds)
    finally:
        revive_node(node)


# =====================================================
# EVENT SENDING
# =====================================================

def send_event(i):
    stat_inc("events_total")
    tried = set()

    event = ClusterEvent(
        event_type="chaos.test",
        payload={
            "msg": f"msg: {i}",
            "seq": i,
            "source": "chaos"
        },
        created_at=time.time()
    )

    for attempt in range(MAX_RETRIES):
        available = [n for n in NODES if n not in tried]

        if not available:
            break

        node = random.choice(available)
        tried.add(node)
        start = time.time()

        try:
            r = requests.post(
                f"{node}/event",
                json=event.model_dump(),
                timeout=REQUEST_TIMEOUT
            )

            elapsed_ms = (time.time() - start) * 1000
            stat_latency(elapsed_ms)

            payload = {}
            try:
                payload = r.json()
            except Exception:
                payload = {"raw_text": r.text}

            if r.status_code == 200:
                leader = None
                if isinstance(payload, dict):
                    if "result" in payload and isinstance(payload["result"], dict):
                        leader = payload["result"].get("leader")
                    else:
                        leader = payload.get("leader")

                if leader:
                    stat_leader(leader)

                stat_inc("events_ok")
                stat_node_ok(node)

                print(
                    f"[TORTURE] "
                    f"{i:03} "
                    f"OK "
                    f"attempt={attempt + 1} "
                    f"node={node} "
                    f"leader={leader} "
                    f"latency={elapsed_ms:.1f}ms"
                )

                return True

            if is_retryable_response(payload) or r.status_code >= 500:
                stat_inc("events_retried")

                if payload.get("error") == "no leader":
                    stat_inc("events_no_leader")

                print(
                    f"[RETRY] "
                    f"{i:03} "
                    f"attempt={attempt + 1} "
                    f"node={node} "
                    f"status={r.status_code} "
                    f"payload={payload}"
                )

                time.sleep(0.5)
                continue

            stat_inc("events_failed")
            stat_node_fail(node)
            stat_unexpected_failure(
                event_index=i,
                attempt=attempt + 1,
                node=node,
                status_code=r.status_code,
                payload=payload,
                reason="hard_fail_non_retryable_response",
            )

            print(
                f"[FAIL] "
                f"{i:03} "
                f"node={node} "
                f"status={r.status_code} "
                f"payload={payload}"
            )

            return False

        except requests.Timeout as e:
            stat_inc("events_timeout")
            stat_inc("events_retried")

            print(
                f"[TIMEOUT] "
                f"{i:03} "
                f"attempt={attempt + 1} "
                f"{node} -> {e}"
            )

        except requests.ConnectionError as e:
            stat_inc("events_connection_error")
            stat_inc("events_retried")

            print(
                f"[CONNECTION] "
                f"{i:03} "
                f"attempt={attempt + 1} "
                f"{node} -> {e}"
            )

        except Exception as e:
            stat_inc("events_forward_error")
            stat_inc("events_retried")
            stat_unexpected_failure(
                event_index=i,
                attempt=attempt + 1,
                node=node,
                reason=f"exception:{type(e).__name__}",
                payload={"exception": str(e)},
            )

            print(
                f"[ERROR] "
                f"{i:03} "
                f"attempt={attempt + 1} "
                f"{node} -> {e}"
            )

        time.sleep(0.5)

    stat_inc("events_failed")
    stat_unexpected_failure(
        event_index=i,
        attempt=MAX_RETRIES,
        node=None,
        reason="dropped_after_retries",
        payload={"tried_nodes": list(tried)},
    )

    print(f"[DROP] {i:03} event dropped after retries")
    return False


# =====================================================
# MAIN LOOP
# =====================================================

def chaos_loop():
    for i in range(EVENTS):
        if random.random() < KILL_PROBABILITY:
            if SLEEP_ONLY_NODE:
                node = SLEEP_ONLY_NODE
            else:
                node = random.choice(NODES)

            seconds = random.uniform(*DEATH_TIME_RANGE)

            t = threading.Thread(
                target=kill_cycle,
                args=(node, seconds),
                daemon=True
            )

            t.start()
            kill_threads.append(t)

        send_event(i)
        time.sleep(random.uniform(*EVENT_DELAY_RANGE))


# =====================================================
# FORCE REVIVE ALL
# =====================================================

def revive_everything():
    print("\n[MAIN] REVIVING ALL NODES\n")

    unique_nodes = sorted(set(NODES))

    for node in unique_nodes:
        try:
            requests.post(f"{node}/revive", timeout=1)
            print(f"[FORCE REVIVE] {node}")
        except Exception as e:
            print(f"[FORCE REVIVE FAIL] {node} -> {e}")


# =====================================================
# WAIT ALL KILL THREADS
# =====================================================

def wait_kills():
    print("\n[MAIN] waiting active kill cycles...\n")

    for t in kill_threads:
        t.join(timeout=30)


# =====================================================
# STATS REPORT
# =====================================================

def print_stats():
    ended_at = time.time()

    print("\n")
    print("=" * 60)
    print("FINAL CHAOS STATS")
    print("=" * 60)

    with stats_lock:
        total = stats["events_total"]
        ok = stats["events_ok"]
        failed = stats["events_failed"]

        success_rate = ((ok / total) * 100) if total else 0

        avg_latency = (
            sum(stats["latency"]) / len(stats["latency"])
            if stats["latency"] else 0
        )

        max_latency = max(stats["latency"]) if stats["latency"] else 0
        min_latency = min(stats["latency"]) if stats["latency"] else 0

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

        print()

        print(f"kills...............: {stats['kills']}")
        print(f"revives.............: {stats['revives']}")

        print()

        print(f"latency_avg.........: {avg_latency:.1f} ms")
        print(f"latency_min.........: {min_latency:.1f} ms")
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
        print("UNEXPECTED FAILURES")
        if stats["unexpected_failures"]:
            for idx, item in enumerate(stats["unexpected_failures"], start=1):
                print(
                    f"  #{idx:02} "
                    f"event={item.get('event_index')} "
                    f"attempt={item.get('attempt')} "
                    f"node={item.get('node')} "
                    f"status={item.get('status_code')} "
                    f"reason={item.get('reason')} "
                    f"payload={item.get('payload')}"
                )
        else:
            print("  none")

        print("=" * 60)

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
                "latency_max": round(max_latency, 3),
                "per_node_ok": dict(stats["per_node_ok"]),
                "per_node_fail": dict(stats["per_node_fail"]),
                "leaders_seen": dict(stats["leaders_seen"]),
            }
        }

        with open(STATS_FILE, "w") as f:
            json.dump(report, f, indent=2)

        print(f"\n[MAIN] stats saved to {STATS_FILE}\n")


# =====================================================
# MAIN
# =====================================================

def main():
    print("[MAIN] starting REAL cluster chaos")
    print_test_config()

    try:
        chaos_loop()
    finally:
        wait_kills()
        revive_everything()
        print_stats()
        print("\n[MAIN] cluster restored\n")


# =====================================================
# ENTRYPOINT
# =====================================================

if __name__ == "__main__":
    main()
