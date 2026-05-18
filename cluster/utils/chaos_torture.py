import time
import random
import requests
import threading

from cluster.runtime.events.cluster_event import ClusterEvent


# =====================================================
# CONFIG
# =====================================================

NODES = [
    "http://100.100.1.200:7000",
    "http://100.100.1.202:7000",
    "http://100.100.1.203:7000",
]

EVENTS = 50
EVENT_DELAY_RANGE = (0.5, 2.0)

KILL_PROBABILITY = 0.25
DEATH_TIME_RANGE = (3, 10)

REQUEST_TIMEOUT = 5


# =====================================================
# KILL / REVIVE
# =====================================================

def kill_node(node):
    try:
        requests.post(f"{node}/kill", timeout=1)
        print(f"[CHAOS] KILL {node}")
    except Exception as e:
        print(f"[CHAOS FAIL KILL] {node} -> {e}")


def revive_node(node):
    try:
        requests.post(f"{node}/revive", timeout=1)
        print(f"[CHAOS] REVIVE {node}")
    except Exception as e:
        print(f"[CHAOS FAIL REVIVE] {node} -> {e}")


def kill_cycle(node, seconds):
    kill_node(node)
    time.sleep(seconds)
    revive_node(node)


# =====================================================
# EVENT SENDING
# =====================================================

def send_event(i):
    node = random.choice(NODES)

    event = ClusterEvent(
        event_type="chaos.test",
        payload={
            "msg": f"message-{i}",
            "seq": i,
            "source": "chaos"
        },
        created_at=time.time()
    )

    try:
        r = requests.post(
            f"{node}/event",
            json=event.model_dump(),
            timeout=REQUEST_TIMEOUT
        )

        print(f"[TORTURE] {i} -> {node} ({r.status_code}) {r.text}")

    except Exception as e:
        print(f"[TORTURE FAIL] {node} -> {e}")


# =====================================================
# MAIN LOOP
# =====================================================

def chaos_loop():

    for i in range(EVENTS):

        if random.random() < KILL_PROBABILITY:
            node = random.choice(NODES)
            seconds = random.uniform(*DEATH_TIME_RANGE)

            threading.Thread(
                target=kill_cycle,
                args=(node, seconds),
                daemon=True
            ).start()

        send_event(i)
        time.sleep(random.uniform(*EVENT_DELAY_RANGE))


def main():
    print("[MAIN] starting REAL cluster chaos (kill/revive)")
    chaos_loop()
    print("[MAIN] done")


if __name__ == "__main__":
    main()
