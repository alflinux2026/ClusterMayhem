
import time
import random
import requests
import threading

from cluster.runtime.events.cluster_event import ClusterEvent


# =====================================================
# CONFIG
# =====================================================

NODES = [
    "http://100.100.1.200:7000", # LEADER

    "http://100.100.1.202:7000", # STANDBY NO WORKER
    "http://100.100.1.202:7000",

    "http://100.100.1.203:7000",# STANDBY WORKER
    "http://100.100.1.203:7000"
]

EVENTS = 20

EVENT_DELAY_RANGE = (0.5, 2.0)

KILL_PROBABILITY = 0.3

DEATH_TIME_RANGE = (5, 15)

REQUEST_TIMEOUT = 5

SLEEP_ONLY_NODE = "http://100.100.1.200:7000"


# =====================================================
# GLOBALS
# =====================================================

kill_threads = []

dead_nodes = set()

dead_lock = threading.Lock()


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

        print(f"[CHAOS] ISOLATE {node}")

    except Exception as e:

        print(f"[CHAOS FAIL ISOLATE] {node} -> {e}")


def revive_node(node):

    try:

        requests.post(
            f"{node}/revive",
            timeout=1
        )

        with dead_lock:
            dead_nodes.discard(node)

        print(f"[CHAOS] REVIVE {node}")

    except Exception as e:

        print(f"[CHAOS FAIL REVIVE] {node} -> {e}")


def kill_cycle(node, seconds):

    try:

        kill_node(node)

        print(f"[CHAOS] ISOLATE {node} for {seconds:.2f}s")

        time.sleep(seconds)

    finally:

        revive_node(node)



# =====================================================
# EVENT SEND WITH FAILOVER
# =====================================================

def send_event(i):

    event = ClusterEvent(
        event_type="chaos.test",
        payload={
            "msg": f"msg: {i}",
            "seq": i,
            "source": "chaos"
        },
        created_at=time.time()
    )

    # random order every try
    candidates = random.sample(NODES, len(NODES))

    last_error = None

    for node in candidates:

        try:

            r = requests.post(
                f"{node}/event",
                json=event.model_dump(),
                timeout=REQUEST_TIMEOUT
            )

            # =========================================
            # HTTP ERROR
            # =========================================

            if r.status_code != 200:

                print(
                    f"[RETRY] {i} {node} "
                    f"http={r.status_code}"
                )

                continue

            # =========================================
            # JSON RESPONSE
            # =========================================

            data = r.json()

            # cluster-level logical errors
            if "error" in data:

                print(
                    f"[RETRY] {i} {node} "
                    f"error={data['error']}"
                )

                last_error = data["error"]

                continue

            # =========================================
            # SUCCESS
            # =========================================

            print(
                f"[TORTURE] {i} -> "
                f"{node} "
                f"OK "
                f"{data}"
            )

            return True

        except Exception as e:

            print(
                f"[RETRY FAIL] {i} {node} -> {e}"
            )

            last_error = str(e)

    # =============================================
    # TOTAL FAILURE
    # =============================================

    print(
        f"[EVENT LOST] {i} "
        f"error={last_error}"
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

            node = random.choice(NODES)

#            node = SLEEP_ONLY_NODE  # 👈 FORZADO

            seconds = random.uniform(*DEATH_TIME_RANGE)

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
            random.uniform(*EVENT_DELAY_RANGE)
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

            print(f"[FORCE REVIVE FAIL] {node} -> {e}")


# =====================================================
# WAIT ALL KILL THREADS
# =====================================================

def wait_kills():

    print("\n[MAIN] waiting active isolated cycles...\n")

    for t in kill_threads:
        t.join(timeout=30)


# =====================================================
# MAIN
# =====================================================

def main():

    print("[MAIN] starting REAL cluster chaos")

    try:

        chaos_loop()

    finally:

        # esperar revive automáticos
        wait_kills()

        # revive final hard safety
        revive_everything()

        print("\n[MAIN] cluster restored\n")


# =====================================================
# ENTRYPOINT
# =====================================================

if __name__ == "__main__":
    main()
