import subprocess
import threading
import time
import random
import requests
from collections import defaultdict

NODES = [
    {"name": "lnx200", "port": 7000},
    {"name": "lnx202", "port": 7000},
    {"name": "lnx203", "port": 7000},
]

TARGETS = [
    "http://100.100.1.200:7000",
    "http://100.100.1.202:7000",
    "http://100.100.1.203:7000",
]

TOTAL_EVENTS = 100
CHAOS_DURATION = 30

processes = {}
sent_seq = set()
stop_flag = False


def start_node(node):
    if node["name"] in processes and processes[node["name"]].poll() is None:
        return

    print(f"[CHAOS] start {node['name']}")

    p = subprocess.Popen(
        ["python", "-m", "cluster.node", "--port", str(node["port"])],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    processes[node["name"]] = p


def stop_node(node):
    p = processes.get(node["name"])
    if p and p.poll() is None:
        print(f"[CHAOS] stop {node['name']}")
        p.terminate()
        try:
            p.wait(timeout=2)
        except:
            p.kill()


def random_chaos():
    start = time.time()

    for n in NODES:
        start_node(n)

    while time.time() - start < CHAOS_DURATION:
        node = random.choice(NODES)
        if random.choice([True, False]):
            stop_node(node)
        else:
            start_node(node)

        time.sleep(random.uniform(0.2, 1.2))

    print("[CHAOS] finished")


def send_event(seq):
    target = random.choice(TARGETS)

    payload = {
        "msg": f"message-{seq}",
        "seq": seq,
        "ts": time.time()
    }

    try:
        r = requests.post(f"{target}/event", json=payload, timeout=2)
        print(f"[TORTURE] {seq} -> {target} ({r.status_code})")
    except Exception as e:
        print(f"[TORTURE] FAIL {seq}: {e}")


def run_torture():
    global stop_flag

    for i in range(TOTAL_EVENTS):
        if stop_flag:
            break

        sent_seq.add(i)
        send_event(i)
        time.sleep(random.uniform(0.05, 0.15))

    print("[TORTURE] finished")


def stop_torture():
    global stop_flag
    stop_flag = True


def fetch_logs():
    seen = set()

    for url in TARGETS:
        try:
            r = requests.get(f"{url}/debug/log", timeout=3)
            for line in r.text.strip().split("\n"):
                try:
                    import json
                    obj = json.loads(line)
                    seq = obj.get("payload", {}).get("seq")
                    if seq is not None:
                        seen.add(seq)
                except:
                    pass
        except Exception as e:
            print(f"[LOG] error {url}: {e}")

    return seen


def main():
    print("[MAIN] starting chaos test")

    chaos_thread = threading.Thread(target=random_chaos)
    torture_thread = threading.Thread(target=run_torture)

    chaos_thread.start()
    torture_thread.start()

    torture_thread.join()
    stop_torture()

    chaos_thread.join()

    print("[MAIN] collecting logs...")

    seen = fetch_logs()
    missing = sorted(list(sent_seq - seen))

    print("\n===== RESULT =====")
    print(f"sent: {len(sent_seq)}")
    print(f"seen: {len(seen)}")
    print(f"missing: {missing}")
    print("==================")


    for n in NODES:
        stop_node(n)


if __name__ == "__main__":
    main()
