class ClusterView:

    def __init__(self):
        self.peers = {}
        self.active_node = None
        self.leases = {}