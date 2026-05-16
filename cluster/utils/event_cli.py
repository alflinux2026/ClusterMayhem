import requests
import sys
import time

from cluster.runtime.events.cluster_event import ClusterEvent


def send_event(node_url, event_type, payload):

    # -----------------------------
    # CREATE CANONICAL EVENT
    # -----------------------------
    event = ClusterEvent(
        event_type=event_type,
        payload=payload,
        created_at=time.time()
    )

    # -----------------------------
    # SEND
    # -----------------------------
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


# -----------------------------
# ENTRYPOINT
# -----------------------------
if __name__ == "__main__":

    if len(sys.argv) < 3:
        print("Usage: python event_cli.py <node_url> <type>")
        print("Example: python event_cli.py http://100.100.1.203:7000 test")
        sys.exit(1)

    node_url = sys.argv[1]
    event_type = sys.argv[2]

    payload = {
        "msg": "hello cluster",
        "seq": int(time.time())
    }

    send_event(node_url, event_type, payload)
