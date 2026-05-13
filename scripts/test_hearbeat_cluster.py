from cluster.workers.heartbeat_worker import HeartbeatWorker
from cluster.lease.lease_manager import LeaseManager

from scripts.test_cluster_basic import ClusterNodeRuntime, NodeState


def main():

    nodes = [
        ClusterNodeRuntime("node-200", 1),
        ClusterNodeRuntime("node-202", 2),
        ClusterNodeRuntime("node-203", 3),
    ]

    # startup
    for n in nodes:
        n.state = NodeState.STANDBY

    nodes[0].state = NodeState.ACTIVE

    lease_manager = LeaseManager()

    hb = HeartbeatWorker(nodes, lease_manager, interval=1.0)

    hb.start(ticks=10)


if __name__ == "__main__":
    main()