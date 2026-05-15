from cluster.runtime.cluster_store import cluster_state
import time


def is_alive(data, timeout=3.0):
    return (time.time() - data["last_seen"]) < timeout


def compute_leader():

    active_nodes = {
        node_id: data
        for node_id, data in cluster_state.items()
        if is_alive(data)
    }

    if not active_nodes:
        return None

    return min(
        active_nodes.items(),
        key=lambda x: (x[1]["priority"], x[0])
    )[0]
