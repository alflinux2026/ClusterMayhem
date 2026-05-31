import time

from cluster.utils.log_print import log_state
from cluster.runtime.cluster_store import cluster_state, get_active_cluster
from cluster.runtime import context as ctx


def compute_alive(timeout=1.5, include_self=False):
    now = time.time()
    alive = {}
    for node_id, node in get_active_cluster().items():
        last_seen = node.get("last_seen", 0)
        if now - last_seen <= timeout:
            alive[node_id] = node
    if include_self and ctx.node_id and ctx.node_id not in alive and ctx.node_id in cluster_state:
        alive[ctx.node_id] = cluster_state[ctx.node_id]
    return alive


def compute_leader():
    alive = compute_alive(include_self=True)
    if not alive:
        return None
    leader_id = min(alive.items(), key=lambda x: (x[1].get("priority", 9999), x[0]))[0]
    return leader_id
