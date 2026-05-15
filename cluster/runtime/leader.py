
from cluster.runtime.cluster_store import get_active_cluster


def is_alive(data, timeout=3.0):

    import time

    return (time.time() - data["last_seen"]) < timeout


def compute_leader():

    active = {
        node_id: data["priority"]
        for node_id, data in get_active_cluster().items()
        if (
            is_alive(data)
            and data["state"] == "ACTIVE"
        )
    }

    if not active:
        return None

    return min(active, key=active.get)
