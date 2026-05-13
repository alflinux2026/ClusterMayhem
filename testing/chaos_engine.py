import random
import time


class ChaosEngine:

    def __init__(self, nodes):
        self.nodes = nodes

    def maybe_kill_node(self, probability=0.1):

        if random.random() < probability:
            node = random.choice(self.nodes)
            print(f"\n💥 CHAOS: killing {node.node_id}\n")
            node.state = node.state.__class__.DEGRADED

    # ---------------------------------------------

    def maybe_partition(self, probability=0.1):

        if random.random() < probability:
            node = random.choice(self.nodes)
            print(f"\n🌐 CHAOS: partitioning {node.node_id}\n")
            node.isolated = True

    # ---------------------------------------------

    def maybe_delay(self, probability=0.2, max_delay=0.3):

        if random.random() < probability:
            delay = random.uniform(0.05, max_delay)
            print(f"\n⏱ CHAOS: delaying cluster {delay:.2f}s\n")
            time.sleep(delay)