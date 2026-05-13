class ElectionEngine:

    @staticmethod
    def can_become_leader(node_id, priority, lease_manager):

        active = lease_manager.active_leader()

        # si ya hay líder válido → no competir
        if active:
            return False

        # no hay líder → cualquier nodo sano puede intentar
        return True