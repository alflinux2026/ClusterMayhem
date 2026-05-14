import json

from cluster.node.node_runtime import NodeRuntime
from cluster.lease.lease_manager import LeaseManager
from cluster.runtime.state import NodeState
from cluster.workers.cluster_worker import ClusterWorker
from cluster.transport.server import register_local_node


register_local_node(
    node_id=node.node_id,
    state=node.state.value,
    priority=node.priority,
)

def load_config():

    with open("cluster/config/nodes.json") as f:
        return json.load(f)


def build_peers(config, self_id):

    return [
        n for n in config["nodes"]
        if n["node_id"] != self_id
    ]


def main(node_id, priority):

    config = load_config()
    peers = build_peers(config, node_id)

    node = NodeRuntime(
        node_id=node_id,
        priority=priority,
        lease_manager=LeaseManager(),
    )

    node.state = NodeState.ACTIVE

    worker = ClusterWorker(node, peers)

    worker.start()


if __name__ == "__main__":

    import sys

    main(
        node_id=sys.argv[1],
        priority=int(sys.argv[2]),
    )
