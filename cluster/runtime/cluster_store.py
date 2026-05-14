import time

cluster_state = {}

NODE_TTL = 5.0  # segundos


def purge_dead_nodes():
    now = time.time()

    dead = [
        n for n, data in cluster_state.items()
        if (now - data.get("last_seen", 0)) > NODE_TTL
    ]

    for n in dead:
        del cluster_state[n]


def get_active_cluster():
    cleanup_cluster()
    return cluster_state


def cleanup_cluster():
    now = time.time()

    to_delete = [
        node_id
        for node_id, data in cluster_state.items()
        if now - data["last_seen"] > NODE_TIMEOUT
    ]

    for node_id in to_delete:
        print(f"[GC] removing {node_id}")
        del cluster_state[node_id]
