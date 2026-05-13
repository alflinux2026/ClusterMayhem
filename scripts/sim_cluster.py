# File: scripts/sim_cluster.py
# Previous: none
# Author: alftorres
# Date: 2026-05-13T18:10:00+0200
# Version: 0.1.0
# Genealogy:
#   scripts/sim_cluster.py 0.1.0 2026-05-13T18:10:00+0200
#   God
#
# Purpose:
#   Minimal local simulator for mayhem-cluster.
#
# Notes:
#   Simulates:
#   - 3 cluster nodes
#   - discovery
#   - leader election
#   - ACTIVE/STANDBY transitions
#   - lease failover
#
# FRV-ID: sim-cluster-3nodes-v0
# Header_End

from enum import Enum
from dataclasses import dataclass


# ============================================================
# STATES
# ============================================================

class NodeState(str, Enum):
    BOOT = "BOOT"
    DISCOVERING = "DISCOVERING"
    STANDBY = "STANDBY"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    ISOLATED = "ISOLATED"
    OFFLINE = "OFFLINE"


# ============================================================
# TRANSITIONS
# ============================================================

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
        NodeState.ISOLATED,
        NodeState.OFFLINE,
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


def can_transition(current, target):
    return target in ALLOWED_TRANSITIONS.get(current, set())


# ============================================================
# MODELS
# ============================================================

@dataclass
class ClusterView:
    active_node: str | None = None


# ============================================================
# RUNTIME
# ============================================================

class ClusterNodeRuntime:

    def __init__(self, node_id: str, priority: int):
        self.node_id = node_id
        self.priority = priority

        self.state = NodeState.BOOT

        self.healthy = True
        self.lease_valid = True
        self.datasets_valid = True

        self.cluster_view = ClusterView()

    # --------------------------------------------------------

    def transition_to(self, target: NodeState):

        if not can_transition(self.state, target):
            raise RuntimeError(
                f"Invalid transition: {self.state} -> {target}"
            )

        print(
            f"[{self.node_id}] "
            f"{self.state} -> {target}"
        )

        self.state = target

    # --------------------------------------------------------

    def is_eligible_for_active(self):

        return (
            self.healthy
            and self.lease_valid
            and self.datasets_valid
            and self.state in (
                NodeState.DISCOVERING,
                NodeState.STANDBY,
            )
        )

    # --------------------------------------------------------

    def summary(self):

        return {
            "node": self.node_id,
            "priority": self.priority,
            "state": self.state.value,
            "active": self.cluster_view.active_node,
        }


# ============================================================
# ELECTION
# ============================================================

def choose_leader(nodes):

    eligible = [
        node
        for node in nodes
        if node.is_eligible_for_active()
    ]

    if not eligible:
        return None

    # menor priority gana
    leader = sorted(
        eligible,
        key=lambda n: n.priority
    )[0]

    return leader


# ============================================================
# CLUSTER
# ============================================================

class ClusterSimulator:

    def __init__(self, nodes):
        self.nodes = nodes

    # --------------------------------------------------------

    def boot_cluster(self):

        print("\n=== BOOT ===\n")

        for node in self.nodes:
            node.transition_to(NodeState.DISCOVERING)

    # --------------------------------------------------------

    def elect_leader(self):

        print("\n=== ELECTION ===\n")

        leader = choose_leader(self.nodes)

        if leader is None:
            print("No eligible leader")
            return

        for node in self.nodes:

            if node == leader:
                node.transition_to(NodeState.ACTIVE)
                node.cluster_view.active_node = leader.node_id

            else:
                node.transition_to(NodeState.STANDBY)
                node.cluster_view.active_node = leader.node_id

        print(f"\nLEADER: {leader.node_id}")

    # --------------------------------------------------------

    def simulate_leader_failure(self):

        print("\n=== LEADER FAILURE ===\n")

        leader = self.get_active_node()

        if not leader:
            print("No active leader")
            return

        print(f"Failing leader: {leader.node_id}")

        leader.healthy = False
        leader.lease_valid = False

        leader.transition_to(NodeState.DEGRADED)

        self.re_elect()

    # --------------------------------------------------------

    def re_elect(self):

        print("\n=== RE-ELECTION ===\n")

        candidates = [
            n for n in self.nodes
            if n.state in (
                NodeState.STANDBY,
                NodeState.DISCOVERING,
            )
        ]

        new_leader = choose_leader(candidates)

        if not new_leader:
            print("No replacement leader available")
            return

        for node in self.nodes:

            if node == new_leader:
                node.transition_to(NodeState.ACTIVE)

            elif node.state != NodeState.DEGRADED:
                node.transition_to(NodeState.STANDBY)

            node.cluster_view.active_node = new_leader.node_id

        print(f"\nNEW LEADER: {new_leader.node_id}")

    # --------------------------------------------------------

    def get_active_node(self):

        for node in self.nodes:
            if node.state == NodeState.ACTIVE:
                return node

        return None

    # --------------------------------------------------------

    def print_cluster(self):

        print("\n=== CLUSTER STATE ===\n")

        for node in self.nodes:
            print(node.summary())


# ============================================================
# MAIN
# ============================================================

def main():

    nodes = [
        ClusterNodeRuntime("node-200", priority=1),
        ClusterNodeRuntime("node-202", priority=2),
        ClusterNodeRuntime("node-203", priority=3),
    ]

    cluster = ClusterSimulator(nodes)

    cluster.boot_cluster()

    cluster.elect_leader()

    cluster.print_cluster()

    cluster.simulate_leader_failure()

    cluster.print_cluster()


if __name__ == "__main__":
    main()