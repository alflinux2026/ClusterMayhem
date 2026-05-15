import time

from cluster.runtime.state import NodeState
from cluster.election.election_engine import ElectionEngine
from cluster.runtime.leader import compute_leader
from cluster.transport.client import broadcast_heartbeat

class NodeRuntime:

    def __init__(self, node_id, priority):

        self.node_id = node_id
        self.priority = priority

        self.state = NodeState.BOOT

        self.last_heartbeat = time.time()

    # -----------------------------------------------------

    def transition(self, new_state):

        if self.state == new_state:
            return

        print(f"[STATE CHANGE] {self.node_id}: {self.state.value} → {new_state.value}")
        self.state = new_state

    # -----------------------------------------------------

    def tick(self):

        print(f"[TICK] {self.node_id} state={self.state.value}")

        if self.state == NodeState.BOOT:
            self.transition(NodeState.STANDBY)
            return

        if self.state == NodeState.STANDBY:

            self.try_become_leader()
            return

        if self.state == NodeState.ACTIVE:
            print(f"[ACTIVE] {self.node_id} acting as leader")

    # -----------------------------------------------------

    def try_become_leader(self):

        print(f"{self.node_id} evaluating leadership...")

        can_lead = ElectionEngine.can_become_leader(
            node_id=self.node_id,
            priority=self.priority
        )

        if can_lead:

            self.transition(NodeState.ACTIVE)



    def emit_heartbeat(self, peers):

        payload = {
            "node_id": self.node_id,
            "state": self.state.value,
            "priority": self.priority,
            "timestamp": time.time(),
        }

        broadcast_heartbeat(peers, payload)




