from __future__ import annotations

import threading
import time

from cluster.runtime.dispatcher import dispatchtick
from cluster.runtime.reconciler.reconcilerloop import reconciletick
from cluster.runtime.state import NodeState
from cluster.runtime import context as ctx
from cluster.runtime.logreplication import replicatelocal


class NodeWorker:
    def __init__(self, node, peers, interval=1.0):
        self.node = node
        self.peers = peers
        self.interval = interval
        self.running = False

    def start(self):
        self.running = True
        t = threading.Thread(target=self.loop, daemon=True)
        t.start()

    def stop(self):
        self.running = False

    def tickstandby(self):
        self.node.emitheartbeat(self.peers)
        reconciletick(self.node)
        replicatelocal()

    def tickactive(self):
        self.node.emitheartbeat(self.peers)
        dispatchtick()
        reconciletick(self.node)
        replicatelocal()

    def tickdegraded(self):
        self.node.emitheartbeat(self.peers)
        replicatelocal()

    def tickbystate(self):
        state = self.node.state
        if state == NodeState.BOOT:
            return
        elif state == NodeState.DISCOVERING:
            return
        elif state == NodeState.STANDBY:
            self.tickstandby()
        elif state == NodeState.ACTIVE:
            self.tickactive()
        elif state == NodeState.DEGRADED:
            self.tickdegraded()
        elif state == NodeState.ISOLATED:
            return
        elif state == NodeState.OFFLINE:
            return

    def loop(self):
        while self.running:
            self.node.tick()
            if self.node.state == NodeState.ISOLATED:
                time.sleep(self.interval)
                continue
            self.tickbystate()
            time.sleep(self.interval)
