
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

    def _loop(self):

        while self._running:

            # -------------------------
            # CLUSTER STATE
            # -------------------------

            self.node.tick()

            self.node.emit_heartbeat(self.peers)

            # -------------------------
            # DISPATCH LOOP
            # -------------------------

            dispatch_tick()

            # -------------------------
            # RECONCILE LOOP
            # -------------------------

            reconcile_tick()

            # -------------------------
            # LOOP SLEEP
            # -------------------------

            time.sleep(self.interval)

