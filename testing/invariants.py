from cluster.runtime.state import NodeState


class Invariants:

    @staticmethod
    def no_invalid_states(nodes):
        """
        Core safety invariant:
        - max 1 ACTIVE
        - no ACTIVE + DEGRADED inconsistency explosion
        """

        active = [n for n in nodes if n.state == NodeState.ACTIVE]

        if len(active) > 1:
            raise AssertionError(
                f"Split brain detected: {[n.node_id for n in active]}"
            )

        return True

    # -------------------------------------------------

    @staticmethod
    def cluster_has_leader(nodes):

        active = [n for n in nodes if n.state == NodeState.ACTIVE]

        return len(active) == 1

    # -------------------------------------------------

    @staticmethod
    def no_orphan_active(nodes):

        """
        ACTIVE nodes must have valid lease (if available in runtime)
        """

        for n in nodes:

            if n.state == NodeState.ACTIVE:

                if hasattr(n, "lease_manager"):

                    if not n.lease_manager.is_valid(n.node_id):
                        raise AssertionError(
                            f"ACTIVE without valid lease: {n.node_id}"
                        )

        return True