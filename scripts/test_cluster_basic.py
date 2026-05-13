# File: scripts/test_cluster_basic.py
# Previous: none
# Author: alftorres
# Date: 2026-05-13T18:35:00+0200
# Version: 0.1.0
# Genealogy:
#   scripts/test_cluster_basic.py 0.1.0 2026-05-13T18:35:00+0200
#   God
#
# Purpose:
#   Minimal executable cluster simulation test.
#
# Notes:
#   Validates:
#   - startup transitions
#   - leader election
#   - ACTIVE/STANDBY assignment
#   - failover
#   - reelection
#
# FRV-ID: test-cluster-basic-v0
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
# CLUSTER VIEW
# ============================================================

@dataclass
class ClusterView:
    active_node: str | None = None


# ============================================================
# NODE RUNTIME
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

    def transition_to(self, target):

        if not can_transition(self.state, target):
            raise RuntimeError(
                f"Invalid transition: "
                f"{self.state} -> {target}"
            )

        print(
            f"[{self.node_id}] "
            f"{self.state.value} -> {target.value}"
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
            "active_node": self.cluster_view.active_node,
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
# CLUSTER TEST
# ============================================================

class ClusterTestRuntime:

    def __init__(self, nodes):
        self.nodes = nodes

    # --------------------------------------------------------

    def startup(self):

        print("\n=== STARTUP ===\n")

        for node in self.nodes:
            node.transition_to(NodeState.DISCOVERING)

    # --------------------------------------------------------

    def elect_leader(self):

        print("\n=== LEADER ELECTION ===\n")

        leader = choose_leader(self.nodes)

        if leader is None:
            raise RuntimeError("No eligible leader")

        for node in self.nodes:

            if node == leader:
                node.transition_to(NodeState.ACTIVE)
            else:
                node.transition_to(NodeState.STANDBY)

            node.cluster_view.active_node = leader.node_id

        print(f"\nLEADER ELECTED: {leader.node_id}")

    # --------------------------------------------------------

    def fail_active_node(self):

        print("\n=== FAIL ACTIVE NODE ===\n")

        active = self.get_active_node()

        if active is None:
            raise RuntimeError("No ACTIVE node found")

        print(f"Failing node: {active.node_id}")

        active.healthy = False
        active.lease_valid = False

        active.transition_to(NodeState.DEGRADED)

    # --------------------------------------------------------

    def reelection(self):

        print("\n=== RE-ELECTION ===\n")

        candidates = [
            node
            for node in self.nodes
            if node.state in (
                NodeState.STANDBY,
                NodeState.DISCOVERING,
            )
        ]

        leader = choose_leader(candidates)

        if leader is None:
            raise RuntimeError("No replacement leader")

        for node in self.nodes:

            if node == leader:
                node.transition_to(NodeState.ACTIVE)

            elif (
                node.state != NodeState.DEGRADED
                and node.state != NodeState.STANDBY
            ):
                node.transition_to(NodeState.STANDBY)

            node.cluster_view.active_node = leader.node_id

        print(f"\nNEW LEADER: {leader.node_id}")

    # --------------------------------------------------------

    def get_active_node(self):

        for node in self.nodes:
            if node.state == NodeState.ACTIVE:
                return node

        return None

    # --------------------------------------------------------

    def print_cluster_state(self):

        print("\n=== CLUSTER STATE ===\n")

        for node in self.nodes:
            print(node.summary())


# ============================================================
# MAIN
# ============================================================

def main():

    nodes = [
        ClusterNodeRuntime(
            node_id="node-200",
            priority=1,
        ),

        ClusterNodeRuntime(
            node_id="node-202",
            priority=2,
        ),

        ClusterNodeRuntime(
            node_id="node-203",
            priority=3,
        ),
    ]

    cluster = ClusterTestRuntime(nodes)

    # startup
    cluster.startup()

    # initial leader election
    cluster.elect_leader()

    cluster.print_cluster_state()

    # simulate leader failure
    cluster.fail_active_node()

    # reelection
    cluster.reelection()

    cluster.print_cluster_state()


if __name__ == "__main__":
    main()