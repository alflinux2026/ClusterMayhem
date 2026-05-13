from cluster.core.state import NodeState
from cluster.core.transitions import can_transition

class ClusterNode:

    def __init__(self, node_id: str):
        self.node_id = node_id
        self.state = NodeState.BOOT

    def set_state(self, new_state: NodeState):
        if not can_transition(self.state, new_state):
            raise Exception(f"Invalid transition {self.state} -> {new_state}")

        self.state = new_state