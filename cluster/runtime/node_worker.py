
import time
import threading

from cluster.runtime.dispatcher import dispatch_tick

from cluster.runtime.reconciler.reconciler_loop import reconcile_tick

class NodeWorker:

    def __init__(self, node, peers, interval=1.0):
        self.node = node
        self.peers = peers
        self.interval = interval
        self._running = False

    def start(self):
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def stop(self):
        self._running = False

# cluster/runtime/node_worker.py

def _loop(self):

    while self._running:

        self.node.tick()
        self.node.emit_heartbeat(self.peers)

        dispatch_tick()

        # FIX: usar self.node
        reconcile_tick(self.node)

        time.sleep(self.interval)
