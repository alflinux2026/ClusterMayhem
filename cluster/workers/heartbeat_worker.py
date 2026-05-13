import time
from cluster.runtime.state import NodeState


class HeartbeatWorker:

    def __init__(self, nodes, lease_manager, interval=1.0):

        self.nodes = nodes
        self.lease_manager = lease_manager
        self.interval = interval

    # -----------------------------------------------------

    def start(self, ticks=5):

        print("\n=== HEARTBEAT START ===\n")

        for i in range(ticks):

            print(f"\n--- tick {i} ---\n")

            self.tick()

            time.sleep(self.interval)

    # -----------------------------------------------------

    def tick(self):

        self.send_heartbeats()
        self.expire_leases()
        self.update_nodes()

    # -----------------------------------------------------

    def send_heartbeats(self):

        for node in self.nodes:

            if node.state == NodeState.ACTIVE:

                self.lease_manager.grant(
                    node.node_id,
                    ttl=2.5
                )

                print(f"HEARTBEAT from {node.node_id}")

    # -----------------------------------------------------

    def expire_leases(self):

        expired = self.lease_manager.expire()

        for node_id in expired:

            print(f"LEASE EXPIRED: {node_id}")

    # -----------------------------------------------------

    def update_nodes(self):

        for node in self.nodes:

            node.tick()

            lease_valid = self.lease_manager.is_valid(
                node.node_id
            )

            # ACTIVE sin lease → degradación lógica
            if node.state == NodeState.ACTIVE and not lease_valid:

                print(
                    f"ACTIVE LOST LEASE: {node.node_id}"
                )

                node.transition(NodeState.DEGRADED)