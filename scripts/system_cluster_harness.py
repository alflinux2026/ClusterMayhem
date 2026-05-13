import time

from cluster.node.node_runtime import NodeRuntime
from cluster.lease.lease_manager import LeaseManager
from cluster.workers.heartbeat_worker import HeartbeatWorker
from cluster.runtime.state import NodeState


# ============================================================
# ASSERT HELPERS
# ============================================================

def assert_single_active(nodes):

    active = [
        n for n in nodes
        if n.state == NodeState.ACTIVE
    ]

    if len(active) != 1:
        raise RuntimeError(
            f"Expected 1 ACTIVE, found {len(active)}"
        )

    print(f"[OK] single ACTIVE: {active[0].node_id}")


# ============================================================
# SIMULATED FAILURE
# ============================================================

def kill_active(nodes):

    for n in nodes:

        if n.state == NodeState.ACTIVE:

            print(f"\n!!! KILLING ACTIVE: {n.node_id}\n")

            n.state = NodeState.DEGRADED


# ============================================================
# MAIN SYSTEM TEST
# ============================================================

def main():

    print("\n==============================")
    print(" CLUSTER SYSTEM HARNESS START")
    print("==============================\n")

    lease_manager = LeaseManager()

    nodes = [
        NodeRuntime("node-200", 1, lease_manager),
        NodeRuntime("node-202", 2, lease_manager),
        NodeRuntime("node-203", 3, lease_manager),
    ]

    # --------------------------------------------------------
    # BOOTSTRAP
    # --------------------------------------------------------

    nodes[0].state = NodeState.ACTIVE
    lease_manager.grant("node-200", ttl=2.5)

    nodes[1].state = NodeState.STANDBY
    nodes[2].state = NodeState.STANDBY

    # --------------------------------------------------------
    # HEARTBEAT LOOP START
    # --------------------------------------------------------

    hb = HeartbeatWorker(nodes, lease_manager, interval=0.5)

    # --------------------------------------------------------
    # PHASE 1: STABLE CLUSTER
    # --------------------------------------------------------

    print("\n=== PHASE 1: STABLE ===\n")

    for _ in range(5):

        hb.tick()

        assert_single_active(nodes)

        time.sleep(0.5)

    # --------------------------------------------------------
    # PHASE 2: FAIL ACTIVE NODE
    # --------------------------------------------------------

    print("\n=== PHASE 2: FAILURE ===\n")

    kill_active(nodes)

    # --------------------------------------------------------
    # PHASE 3: SELF-HEALING
    # --------------------------------------------------------

    print("\n=== PHASE 3: SELF-HEAL ===\n")

    for i in range(10):

        print(f"\n--- recovery tick {i} ---\n")

        hb.tick()

        time.sleep(0.5)

        # intentar validar si ya convergió
        try:
            assert_single_active(nodes)
            print("\n[SUCCESS] Cluster converged\n")
            break
        except RuntimeError as e:
            print(f"[WAIT] {e}")


    # --------------------------------------------------------
    # FINAL STATE
    # --------------------------------------------------------

    print("\n=== FINAL STATE ===\n")

    for n in nodes:

        print(
            {
                "node": n.node_id,
                "state": n.state.value
            }
        )


if __name__ == "__main__":
    main()