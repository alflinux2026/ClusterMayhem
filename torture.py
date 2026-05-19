import time
import requests
import uuid
from cluster.utils.chaos_controller import ChaosController

TARGETS = [
    "http://100.100.1.200:7000",
    "http://100.100.1.202:7000",
    "http://100.100.1.203:7000",
]

TOTAL_MESSAGES = 100
SLEEP_BETWEEN = 0.2


def send_event(seq: int):
    payload = {
        "event_id": str(uuid.uuid4()),
        "event_type": "test",
        "schema_version": "0.1",
        "payload": {
            "msg": f"message-{seq}",
            "seq": seq,
            "ts": time.time(),
        }
    }

    # round robin simple
    target = TARGETS[seq % len(TARGETS)]
    url = f"{target}/event"

    try:
        r = requests.post(url, json=payload, timeout=2)
        print(f"[SEND] seq={seq} -> {target} status={r.status_code}")
    except Exception as e:
        print(f"[SEND ERROR] seq={seq} -> {target}: {e}")


def main():
    chaos = ChaosController(min_interval=2, max_interval=6)

    print("[START] Chaos controller starting")
    chaos.start()

    try:
        for i in range(TOTAL_MESSAGES):
            send_event(i)
            time.sleep(SLEEP_BETWEEN)

    finally:
        print("[STOP] Stopping chaos controller")
        chaos.stop()


if __name__ == "__main__":
    main()
