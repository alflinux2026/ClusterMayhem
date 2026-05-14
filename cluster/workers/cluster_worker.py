import time


class ClusterWorker:

    def __init__(self, node, peers, interval=1.0):

        self.node = node
        self.peers = peers
        self.interval = interval
        self.running = False

    # -----------------------------------------

    def start(self):

        self.running = True

        print(f"[{self.node.node_id}] CLUSTER WORKER STARTED")

        while self.running:

            self.tick()

            time.sleep(self.interval)

    # -----------------------------------------

    def stop(self):

        self.running = False

    # -----------------------------------------

    def tick(self):

        self.node.emit_heartbeat(self.peers)
