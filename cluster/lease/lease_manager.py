import time


class Lease:

    def __init__(self, owner, ttl):

        self.owner = owner
        self.ttl = ttl
        self.created = time.time()

    def is_valid(self):

        return time.time() < self.created + self.ttl


class LeaseManager:

    def __init__(self):

        self.leases = {}

    # -----------------------------------------------------

    def grant(self, node_id, ttl):

        self.leases[node_id] = Lease(node_id, ttl)

    # -----------------------------------------------------

    def is_valid(self, node_id):

        lease = self.leases.get(node_id)

        return lease.is_valid() if lease else False

    # -----------------------------------------------------

    def expire(self):

        expired = []

        for node_id, lease in list(self.leases.items()):

            if not lease.is_valid():

                expired.append(node_id)
                del self.leases[node_id]

        return expired

    # -----------------------------------------------------

    def active_leader(self):

        for node_id, lease in self.leases.items():

            if lease.is_valid():

                return node_id

        return None

    # -----------------------------------------------------

    def get_active_nodes(self):

        active = []

        for node_id, lease in self.leases.items():

            if lease.is_valid():

                active.append(node_id)

        return active