import requests
import sys
import time
import itertools

from cluster.runtime.events.cluster_event import ClusterEvent


# -----------------------------
# SEND (UNCHANGED LOGIC)
# -----------------------------
def send_event(node_url, event_type, payload):
    event = ClusterEvent(
        event_type=event_type,
        payload=payload,
        created_at=time.time()
    )

    r = requests.post(
        f"{node_url}/event",
        json=event.model_dump(),
        timeout=3
    )

    print(f"[CLIENT] sent to {node_url}")

    try:
        print(f"[RESPONSE] {r.json()}")
    except Exception:
        print(f"[RESPONSE RAW] {r.text}")

    return r.status_code == 200


def check_node_health(node_url):
    try:
        r = requests.get(f"{node_url}/health", timeout=1)
        return r.status_code == 200
    except Exception:
        return False

def print_cluster_health(node_urls):
    print("\n[CLUSTER HEALTH CHECK]")

    healthy = []
    unhealthy = []

    for node in node_urls:
        ok = check_node_health(node)

        if ok:
            print(f"  [OK]   {node}")
            healthy.append(node)
        else:
            print(f"  [DOWN] {node}")
            unhealthy.append(node)

    return healthy, unhealthy

# -----------------------------
# CLUSTER LOOP (NEW)
# -----------------------------
def send_to_cluster(node_urls, event_type, payload, max_cycles=None, debug_health=False):

    if debug_health:
        healthy, _ = print_cluster_health(node_urls)

        # opcional: si quieres SOLO nodos vivos
        if healthy:
            node_urls = healthy

    backoff = 1
    max_backoff = 10
    node_count = len(node_urls)

    for i in range(max_cycles or 10**9):

        node = node_urls[i % node_count]

        print(f"\n[CYCLE {i}] trying {node}")

        try:
            ok = send_event(node, event_type, payload)

            if ok:
                print("[CLIENT] event delivered successfully")
                return

        except requests.RequestException as e:
            print(f"[ERROR] {node} -> {e}")

        if (i + 1) % node_count == 0:
            print(f"[CLUSTER] full round failed → retry in {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)


# -----------------------------
# ENTRYPOINT
# -----------------------------
if __name__ == "__main__":

    if len(sys.argv) < 3:
        print("Usage: python event_cli.py <node1,node2,...> <type> [--debug-cluster-health]")
        sys.exit(1)

    node_urls = sys.argv[1].split(",")
    event_type = sys.argv[2]

    debug_health = "--debug-cluster-health" in sys.argv

    payload = {
        "msg": "hello cluster from event_cli",
        "seq": int(time.time())
    }
    send_to_cluster(
        node_urls,
        event_type,
        payload,
        debug_health=debug_health
    )
