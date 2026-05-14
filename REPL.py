from cluster.node.node_runtime import NodeRuntime
from cluster.lease.lease_manager import LeaseManager
from cluster.config.loader import load_peers
from cluster.runtime.state import NodeState

peers = load_peers()

node = NodeRuntime(
    node_id="lnx203hp",
    priority=3,
    lease_manager=LeaseManager(),
)

node.state = NodeState.ACTIVE

node.emit_heartbeat(peers)
