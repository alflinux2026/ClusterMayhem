import time

from cluster.runtime.cluster_store import cluster_state
from cluster.runtime import context as ctx

LEADER_ALIVE_TIMEOUT = 1.5


def refresh_self_alive_entry(now=None):
    now = now or time.time()
    if not getattr(ctx, "node", None):
        return
    existing = cluster_state.get(ctx.node_id, {})
    cluster_state[ctx.node_id] = {
        "state": ctx.node.state.value,
        "priority": ctx.node.priority,
        "last_seen": now,
        "log_meta": existing.get("log_meta", {}),
    }


def is_alive(data, timeout=LEADER_ALIVE_TIMEOUT, now=None):
    now = now or time.time()
    return (now - data.get("last_seen", 0)) < timeout


def compute_alive(timeout=LEADER_ALIVE_TIMEOUT, include_self=True):
    now = time.time()
    if include_self:
        refresh_self_alive_entry(now)
    active_nodes = {}
    for node_id, data in cluster_state.items():
        alive = is_alive(data, timeout=timeout, now=now)
        if alive:
            active_nodes[node_id] = data
        else:
            data["state"] = "GONE"
    return active_nodes


def compute_leader(debug_node_id=None, timeout=LEADER_ALIVE_TIMEOUT):
    active_nodes = compute_alive(timeout=timeout, include_self=True)
    if not active_nodes:
        return None
    return min(active_nodes.items(), key=lambda x: (x[1]["priority"], x[0]))[0]
