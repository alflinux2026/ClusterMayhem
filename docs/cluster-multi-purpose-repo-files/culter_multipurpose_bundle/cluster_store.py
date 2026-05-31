import time

cluster_state = {}
NODE_TTL = 5.0


def cleanup_cluster():
    now = time.time()
    to_delete = [node_id for node_id, data in list(cluster_state.items()) if (now - data.get("last_seen", 0)) > NODE_TTL]
    for node_id in to_delete:
        print(f"[GC] removing {node_id}")
        del cluster_state[node_id]


def get_active_cluster():
    cleanup_cluster()
    return cluster_state
