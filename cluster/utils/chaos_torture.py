import time
import random
import threading
import requests

from cluster.runtime.events.cluster_event import ClusterEvent


# =========================
# CONFIG
# =========================
NODES = [
    "http://100.100.1.200:7000",
    "http://100.100.1.202:7000",
    "http://100.100.1.203:7000",
]

TOTAL_EVENTS = 100


# =========================
# BOOT CONTROL
# =========================
def boot_on(node):
    try:
        requests.post(f"{node}/debug/boot/on", timeout=1)
        print(f"[CHAOS] BOOT ON {node}")
    except Exception as e:
        print(f"[BOOT ERROR ON] {node}: {e}")


def boot_off(node):
    try:
        requests.post(f"{node}/debug/boot/off", timeout=1)
        print(f"[CHAOS] BOOT OFF {node}")
    except Exception as e:
        print(f"[BOOT ERROR OFF] {node}: {e}")


def boot_cycle(node):
    duration = random.uniform(1.5, 5.0)
    boot_on(node)
    time.sleep(duration)
    boot_off(node)


def chaos_boot_loop(stop_event):
    while not stop_event.is_set():
        node = random.choice(NODES)
        boot_cycle(node)
        time.sleep(random.uniform(0.5, 2.0))


# =========================
# EVENT SENDER
# =========================
def send_event(i):
    node = random.choice(NODES)

    event = {
        "event_id": i,
        "event_type": "test",
        "payload": {"value": i}
    }

    try:
        r = requests.post(f"{node}/event", json=event, timeout=2)
        if r.status_code != 200:
            print(f"[TORTURE FAIL {i}] {r.text}")
        else:
            print(f"[TORTURE OK {i}]")
            return True

    except Exception as e:
        print(f"[TORTURE FAIL {i}] {e}")

    return False


# =========================
# MAIN
# =========================
def main():

    print("[MAIN] starting chaos torture")

    stop_boot = threading.Event()

    # BOOT chaos thread
    boot_thread = threading.Thread(
        target=chaos_boot_loop,
        args=(stop_boot,),
        daemon=True
    )
    boot_thread.start()

    seen = 0

    try:
        for i in range(TOTAL_EVENTS):
            if send_event(i):
                seen += 1

            time.sleep(random.uniform(0.05, 0.2))

    finally:
        print("[MAIN] stopping BOOT chaos...")
        stop_boot.set()
        boot_thread.join(timeout=3)

        # cleanup safety
        for n in NODES:
            boot_off(n)

    print("\n===== RESULT =====")
    print(f"sent: {TOTAL_EVENTS}")
    print(f"seen: {seen}")
    print(f"missing: {TOTAL_EVENTS - seen}")
    print("==================")



if __name__ == "__main__":
    main()
