import random
import time
import threading
from cluster import restart, kill, NODES

class ChaosEngine:

    def __init__(self):
        self.running = False
        self.thread = None

    def _loop(self):
        print("[CHAOS] started")

        while self.running:
            node = random.choice(NODES)

            action = random.choice(["restart", "kill"])

            if action == "restart":
                print(f"[CHAOS] restart {node}")
                restart(node)
            else:
                print(f"[CHAOS] kill {node}")
                kill(node)

            time.sleep(random.randint(1, 4))

        print("[CHAOS] stopped")

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._loop)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
