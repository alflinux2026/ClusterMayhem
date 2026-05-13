from cluster.core.state import NodeState

ALLOWED_TRANSITIONS = {
    NodeState.BOOT: {
        NodeState.DISCOVERING,
    },
    NodeState.DISCOVERING: {
        NodeState.STANDBY,
        NodeState.ACTIVE,
        NodeState.ISOLATED,
    },
    NodeState.STANDBY: {
        NodeState.ACTIVE,
        NodeState.DEGRADED,
        NodeState.OFFLINE,
        NodeState.ISOLATED,
    },
    NodeState.ACTIVE: {
        NodeState.STANDBY,
        NodeState.DEGRADED,
        NodeState.OFFLINE,
    },
    NodeState.DEGRADED: {
        NodeState.STANDBY,
        NodeState.OFFLINE,
    },
    NodeState.ISOLATED: {
        NodeState.DISCOVERING,
        NodeState.OFFLINE,
    },
}

def can_transition(from_state: NodeState, to_state: NodeState) -> bool:
    return to_state in ALLOWED_TRANSITIONS.get(from_state, set())