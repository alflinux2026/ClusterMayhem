from cluster.runtime.cluster_store import get_active_cluster

class ElectionEngine:

    @staticmethod
    def can_become_leader(node_id, priority):

        active_nodes = get_active_cluster()

        # si hay líder activo estable, no competir
        if any(n["state"] == "ACTIVE" for n in active_nodes.values()):
            return False

        return True
