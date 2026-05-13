import time
import random

from cluster.node.node_runtime import NodeRuntime
from cluster.lease.lease_manager import LeaseManager
from cluster.workers.heartbeat_worker import HeartbeatWorker

from testing.chaos_engine import ChaosEngine
from testing.invariants import Invariants


def main():

    lease_manager = LeaseManager()

    nodes = [
        NodeRuntime("node-200", 1, lease_manager),
        NodeRuntime("node-202", 2, lease_manager),
        NodeRuntime("node-203", 3, lease_manager),
    ]

    # bootstrap
    nodes[0].state = nodes[0].state.__class__.ACTIVE
    lease_manager.grant("node-200", ttl=2.5)

    hb = HeartbeatWorker(nodes, lease_manager, interval=0.2)
    chaos = ChaosEngine(nodes)

    print("\n🔥 CHAOS TEST START\n")

    for tick in range(50):

        print(f"\n--- TICK {tick} ---")

        # 1. apply chaos BEFORE tick
        chaos.maybe_kill_node(0.1)
        chaos.maybe_partition(0.1)
        chaos.maybe_delay()

        # 2. normal system tick
        hb.tick()

        # 3. invariants check (auto validation loop)
        try:

            Invariants.no_invalid_states(nodes)

            print("✔ invariants OK")

        except AssertionError as e:

            print(f"❌ INVARIANT VIOLATION: {e}")

        time.sleep(0.2)


if __name__ == "__main__":
    main()