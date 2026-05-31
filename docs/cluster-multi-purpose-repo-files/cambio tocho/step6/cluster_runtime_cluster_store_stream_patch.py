import time

cluster_state = {}


def get_active_cluster():
    return cluster_state


def upsert_node(node_id: str, payload: dict):
    current = cluster_state.get(node_id, {})
    cluster_state[node_id] = {
        **current,
        **payload,
        "last_seen": time.time(),
    }
    return cluster_state[node_id]


def get_node(node_id: str) -> dict:
    return cluster_state.get(node_id, {})
