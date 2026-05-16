import time

from cluster.runtime.state import NodeState
from cluster.runtime.leader import compute_leader
from cluster.runtime.cluster_store import cluster_state

import requests


class NodeRuntime:

    def __init__(self, node_id, priority):
        self.node_id = node_id
        self.priority = priority

        self.state = NodeState.BOOT
        self.last_heartbeat = time.time()

    # -----------------------------------------------------
    # STATE TRANSITION
    # -----------------------------------------------------

    def transition(self, new_state):

        if self.state == new_state:
            return

        print(f"[{self.node_id}] {self.state} -> {new_state}")
        self.state = new_state

    # -----------------------------------------------------
    # MAIN TICK LOOP
    # -----------------------------------------------------

    def tick(self):

#        print(f"[TICK] {self.node_id} state={self.state.value}")
        print(f"[STATE] {self.state.value}")

        # BOOT -> STANDBY (una sola vez)
        if self.state == NodeState.BOOT:
            self.transition(NodeState.STANDBY)
            return

        # -------------------------------------------------
        # GLOBAL LEADER DECISION (external authority)
        # -------------------------------------------------

        leader = compute_leader()

#        print(f"[LEADER] computed leader = {leader}")
        print(f"[LEADER] {leader}")

        # -------------------------------------------------
        # APPLY RESULT (no decision, only reflection)
        # -------------------------------------------------

        if leader == self.node_id:
            if self.state != NodeState.ACTIVE:
                print(f"[{self.node_id}] becoming ACTIVE")
                self.transition(NodeState.ACTIVE)
        else:
            if self.state != NodeState.STANDBY:
                print(f"[{self.node_id}] becoming STANDBY")
                self.transition(NodeState.STANDBY)

    # -----------------------------------------------------
    # HEARTBEAT (ONLY TELEMETRY)
    # -----------------------------------------------------


    def emit_heartbeat(self, peers):

        hb = {
            "node_id": self.node_id,
            "state": self.state.value,
            "priority": self.priority,
        }

        for peer in peers:
            url = f"http://{peer['host']}:{peer['port']}/heartbeat"

            try:
                requests.post(url, json=hb, timeout=2)

            except requests.exceptions.RequestException:
                pass  # nodo offline = estado normal del cluster
