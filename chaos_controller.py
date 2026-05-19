import random
import time
import subprocess
import threading
import signal
import sys

NODES = [
    "lnx200nas",
    "lnx202pc",
    "lnx203hp",
]

class ChaosController:
    def __init__(self, min_interval=3, max_interval=10):
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.running = False
        self.thread = None

    def start_node(self, node):
        print(f"[CHAOS] Starting {node}")
        subprocess.run(["docker", "start", node], stdout=subprocess.DEVNULL)

    def stop_node(self, node):
        print(f"[CHAOS] Stopping {node}")
        subprocess.run(["docker", "stop", node], stdout=subprocess.DEVNULL)

    def loop(self):
        self.running = True
        while self.running:
            node = random.choice(NODES)
            action = random.choice(["stop", "start"])

            try:
                if action == "stop":
                    self.stop_node(node)
                else:
                    self.start_node(node)
            except Exception as e:
                print(f"[CHAOS] error: {e}")

            time.sleep(random.uniform(self.min_interval, self.max_interval))

    def start(self):
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
