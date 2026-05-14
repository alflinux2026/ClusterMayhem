import time

from cluster.transport.server import register_local_node

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

        # 👇 registrar self localmente
        register_local_node(
            node_id=self.node.node_id,
            state=self.node.state.value,
            priority=self.node.priority,
        )

        # 👇 enviar a peers
        self.node.emit_heartbeat(self.peers)
