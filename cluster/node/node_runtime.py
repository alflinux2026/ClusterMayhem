import time

from cluster.runtime.state import NodeState
from cluster.election.election_engine import ElectionEngine

from cluster.transport.client import broadcast_heartbeat

class NodeRuntime:

    def __init__(self, node_id, priority, lease_manager: LeaseManager):

        self.node_id = node_id
        self.priority = priority

        self.state = NodeState.BOOT

        self.last_heartbeat = time.time()

    # -----------------------------------------------------

    def transition(self, new_state):

        if self.state == new_state:
            return

        print(f"[{self.node_id}] {self.state} -> {new_state}")
        self.state = new_state

    # -----------------------------------------------------

    def tick(self):

        """
        Called by heartbeat loop
        """

        # STANDBY sin líder → posible election trigger
        if self.state == NodeState.STANDBY:

            active_nodes = self.lease_manager.get_active_nodes()

            if not active_nodes:

                self.try_become_leader()

    # -----------------------------------------------------

    def try_become_leader(self):

        print(f"{self.node_id} evaluating leadership...")

        can_lead = ElectionEngine.can_become_leader(
            node_id=self.node_id,
            priority=self.priority
        )

        if can_lead:

            self.transition(NodeState.ACTIVE)

            self.lease_manager.grant(
                self.node_id,
                ttl=2.5
            )

    def emit_heartbeat(self, peers):

        payload = {
            "node_id": self.node_id,
            "state": self.state.value,
            "leader": self.lease_manager.active_leader(),
            "priority": self.priority,
            "timestamp": time.time(),
        }

        broadcast_heartbeat(peers, payload)


