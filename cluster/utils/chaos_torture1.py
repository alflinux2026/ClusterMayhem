import time
import random
import requests
import threading

NODES = [
    "http://100.100.1.200:7000",
    "http://100.100.1.202:7000",
    "http://100.100.1.203:7000",
]

EVENTS = 100


def boot_node(node, seconds):
    try:
        requests.post(
            f"{node}/boot",
            json={"seconds": seconds},
            timeout=1
        )
        print(f"[CHAOS] BOOT {node} {seconds:.2f}s")
    except Exception as e:
        print(f"[CHAOS FAIL] {node} -> {e}")


def send_event(i):
    node = random.choice(NODES)

    payload = {
        "event_id": str(i),   # 🔥 FIX CRÍTICO (tu bug)
        "event_type": "test",
        "data": {"i": i}
    }

    try:
        r = requests.post(
            f"{node}/event",
            json=payload,
            timeout=2
        )
        if r.status_code != 200:
            print(f"[FAIL {i}] {r.text}")
    except Exception as e:
        print(f"[FAIL {i}] {e}")


def chaos_loop():
    for i in range(EVENTS):

        # random BOOT bursts
        if random.random() < 0.15:
            node = random.choice(NODES)
            threading.Thread(
                target=boot_node,
                args=(node, random.uniform(0.3, 1.2)),
                daemon=True
            ).start()

        send_event(i)
        time.sleep(random.uniform(0.01, 0.05))


def main():
    print("[MAIN] starting chaos torture")
    chaos_loop()
    print("[MAIN] done")


if __name__ == "__main__":
    main()
