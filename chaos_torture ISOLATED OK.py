import time
import json
import random
import requests
import threading
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

EVENTS = 100

EVENT_DELAY_RANGE = (0.2, 1.0)

KILL_PROBABILITY = 0.10

DEATH_TIME_RANGE = (5, 10)

REQUEST_TIMEOUT = 5

MAX_RETRIES = 10

SLEEP_ONLY_NODE = None
# SLEEP_ONLY_NODE = "http://100.100.1.200:7000"


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
    "kills": 0,
    "revives": 0,
    "per_node_ok": defaultdict(int),
    "per_node_fail": defaultdict(int),
    "leaders_seen": defaultdict(int),
    "latency": [],
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


# =====================================================
# KILL / REVIVE
# =====================================================

def kill_node(node):

    try:

        requests.post(
            f"{node}/sleep",
            timeout=1
        )

        with dead_lock:
            dead_nodes.add(node)

        stat_inc("kills")

        print(f"[CHAOS] SLEEP {node}")

    except Exception as e:

        print(f"[CHAOS FAIL SLEEP] {node} -> {e}")


def revive_node(node):

    try:

        requests.post(
            f"{node}/revive",
            timeout=1
        )

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

        available = [
            n for n in NODES
            if n not in tried
        ]

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

            elapsed_ms = (
                time.time() - start
            ) * 1000

            stat_latency(elapsed_ms)

            payload = {}

            try:
                payload = r.json()
            except Exception:
                pass

            if r.status_code == 200 and "result" in payload:

                result = payload["result"]

                leader = result.get("leader")

                if leader:
                    stat_leader(leader)

                stat_inc("events_ok")

                stat_node_ok(node)

                print(
                    f"[TORTURE] "
                    f"{i:03} "
                    f"OK "
                    f"attempt={attempt+1} "
                    f"node={node} "
                    f"leader={leader} "
                    f"latency={elapsed_ms:.1f}ms"
                )

                return True

            # retryable cluster errors
            if is_retryable_response(payload):

                stat_inc("events_retried")

                if payload.get("error") == "no leader":
                    stat_inc("events_no_leader")

                print(
                    f"[RETRY] "
                    f"{i:03} "
                    f"attempt={attempt+1} "
                    f"node={node} "
                    f"payload={payload}"
                )

                time.sleep(0.5)

                continue

            # hard fail
            stat_inc("events_failed")

            stat_node_fail(node)

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
                f"attempt={attempt+1} "
                f"{node} -> {e}"
            )

        except requests.ConnectionError as e:

            stat_inc("events_connection_error")
            stat_inc("events_retried")

            print(
                f"[CONNECTION] "
                f"{i:03} "
                f"attempt={attempt+1} "
                f"{node} -> {e}"
            )

        except Exception as e:

            stat_inc("events_forward_error")
            stat_inc("events_retried")

            print(
                f"[ERROR] "
                f"{i:03} "
                f"attempt={attempt+1} "
                f"{node} -> {e}"
            )

        time.sleep(0.5)

    stat_inc("events_failed")

    print(
        f"[DROP] "
        f"{i:03} "
        f"event dropped after retries"
    )

    return False


# =====================================================
# MAIN LOOP
# =====================================================

def chaos_loop():

    for i in range(EVENTS):

        # =============================================
        # RANDOM NODE DEATH
        # =============================================

        if random.random() < KILL_PROBABILITY:

            if SLEEP_ONLY_NODE:
                node = SLEEP_ONLY_NODE
            else:
                node = random.choice(NODES)

            seconds = random.uniform(
                *DEATH_TIME_RANGE
            )

            t = threading.Thread(
                target=kill_cycle,
                args=(node, seconds),
                daemon=True
            )

            t.start()

            kill_threads.append(t)

        # =============================================
        # SEND EVENT
        # =============================================

        send_event(i)

        time.sleep(
            random.uniform(
                *EVENT_DELAY_RANGE
            )
        )


# =====================================================
# FORCE REVIVE ALL
# =====================================================

def revive_everything():

    print("\n[MAIN] REVIVING ALL NODES\n")

    unique_nodes = sorted(set(NODES))

    for node in unique_nodes:

        try:

            requests.post(
                f"{node}/revive",
                timeout=1
            )

            print(f"[FORCE REVIVE] {node}")

        except Exception as e:

            print(
                f"[FORCE REVIVE FAIL] "
                f"{node} -> {e}"
            )


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

    print("\n")
    print("=" * 60)
    print("FINAL CHAOS STATS")
    print("=" * 60)

    with stats_lock:

        total = stats["events_total"]
        ok = stats["events_ok"]
        failed = stats["events_failed"]

        success_rate = (
            (ok / total) * 100
            if total else 0
        )

        avg_latency = (
            sum(stats["latency"]) /
            len(stats["latency"])
            if stats["latency"] else 0
        )

        max_latency = (
            max(stats["latency"])
            if stats["latency"] else 0
        )

        min_latency = (
            min(stats["latency"])
            if stats["latency"] else 0
        )

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

        print()

        print(f"kills...............: {stats['kills']}")
        print(f"revives.............: {stats['revives']}")

        print()

        print(f"latency_avg.........: {avg_latency:.1f} ms")
        print(f"latency_min.........: {min_latency:.1f} ms")
        print(f"latency_max.........: {max_latency:.1f} ms")

        print()
        print("LEADERS SEEN")

        for leader, count in sorted(
            stats["leaders_seen"].items()
        ):
            print(f"  {leader:15} -> {count}")

        print()
        print("NODE SUCCESS")

        for node, count in sorted(
            stats["per_node_ok"].items()
        ):
            print(f"  {node:30} -> {count}")

        print()
        print("NODE FAIL")

        for node, count in sorted(
            stats["per_node_fail"].items()
        ):
            print(f"  {node:30} -> {count}")

        print("=" * 60)

        with open(
            "chaos_stats.json",
            "w"
        ) as f:

            json.dump(
                {
                    **stats,
                    "per_node_ok": dict(stats["per_node_ok"]),
                    "per_node_fail": dict(stats["per_node_fail"]),
                    "leaders_seen": dict(stats["leaders_seen"]),
                },
                f,
                indent=2
            )

        print("\n[MAIN] stats saved to chaos_stats.json\n")


# =====================================================
# MAIN
# =====================================================

def main():

    print("[MAIN] starting REAL cluster chaos")

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
