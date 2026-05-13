# File: scripts/test_split_brain.py
# Previous: none
# Author: alftorres
# Date: 2026-05-13T18:52:00+0200
# Version: 0.1.0
# Genealogy:
#   scripts/test_split_brain.py 0.1.0 2026-05-13T18:52:00+0200
#   God
#
# Purpose:
#   Simulate and resolve split-brain scenarios.
#
# Notes:
#   Validates:
#   - multiple ACTIVE detection
#   - deterministic authority resolution
#   - forced demotion
#   - invariant restoration
#
# FRV-ID: test-split-brain-v0
# Header_End

from enum import Enum


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
    },

    NodeState.STANDBY: {
        NodeState.ACTIVE,
        NodeState.DEGRADED,
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
}


def can_transition(current, target):
    return target in ALLOWED_TRANSITIONS.get(current, set())


# ============================================================
# NODE
# ============================================================

class ClusterNode:

    def __init__(self, node_id, priority):

        self.node_id = node_id
        self.priority = priority

        self.state = NodeState.BOOT

    # --------------------------------------------------------

    def transition_to(self, target):

        if self.state == target:
            return

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

    def summary(self):

        return {
            "node": self.node_id,
            "priority": self.priority,
            "state": self.state.value,
        }


# ============================================================
# SPLIT BRAIN
# ============================================================

def detect_multiple_active(nodes):

    active_nodes = [
        node
        for node in nodes
        if node.state == NodeState.ACTIVE
    ]

    return active_nodes


# ------------------------------------------------------------

def resolve_split_brain(nodes):

    active_nodes = detect_multiple_active(nodes)

    if len(active_nodes) <= 1:
        print("\nNo split-brain detected")
        return

    print("\n=== SPLIT-BRAIN DETECTED ===\n")

    for node in active_nodes:
        print(
            f"ACTIVE NODE: "
            f"{node.node_id} "
            f"(priority={node.priority})"
        )

    # menor priority gana
    winner = sorted(
        active_nodes,
        key=lambda n: (n.priority, n.node_id)
    )[0]

    print(
        f"\nWINNER: {winner.node_id}"
    )

    for node in active_nodes:

        if node == winner:
            continue

        print(
            f"Demoting {node.node_id}"
        )

        node.transition_to(NodeState.STANDBY)

    print("\n=== SPLIT-BRAIN RESOLVED ===")


# ============================================================
# INVARIANTS
# ============================================================

def assert_single_active(nodes):

    active_nodes = [
        node
        for node in nodes
        if node.state == NodeState.ACTIVE
    ]

    if len(active_nodes) > 1:
        raise RuntimeError(
            "Invariant violation: "
            "multiple ACTIVE nodes"
        )

    print(
        "\nInvariant OK: "
        "single ACTIVE node"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    node_200 = ClusterNode(
        node_id="node-200",
        priority=1,
    )

    node_202 = ClusterNode(
        node_id="node-202",
        priority=2,
    )

    node_203 = ClusterNode(
        node_id="node-203",
        priority=3,
    )

    nodes = [
        node_200,
        node_202,
        node_203,
    ]

    print("\n=== STARTUP ===\n")

    for node in nodes:
        node.transition_to(NodeState.DISCOVERING)

    # --------------------------------------------------------
    # NORMAL CLUSTER
    # --------------------------------------------------------

    print("\n=== NORMAL STATE ===\n")

    node_200.transition_to(NodeState.ACTIVE)

    node_202.transition_to(NodeState.STANDBY)

    node_203.transition_to(NodeState.STANDBY)

    for node in nodes:
        print(node.summary())

    assert_single_active(nodes)

    # --------------------------------------------------------
    # FORCE SPLIT-BRAIN
    # --------------------------------------------------------

    print("\n=== FORCING SPLIT-BRAIN ===\n")

    node_202.transition_to(NodeState.ACTIVE)

    for node in nodes:
        print(node.summary())

    # --------------------------------------------------------
    # RESOLUTION
    # --------------------------------------------------------

    resolve_split_brain(nodes)

    # --------------------------------------------------------
    # FINAL STATE
    # --------------------------------------------------------

    print("\n=== FINAL CLUSTER STATE ===\n")

    for node in nodes:
        print(node.summary())

    assert_single_active(nodes)


if __name__ == "__main__":
    main()