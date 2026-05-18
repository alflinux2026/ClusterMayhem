import time

cluster_state = {}

NODE_TTL = 5.0  # segundos


def cleanup_cluster():
    now = time.time()

    for node_id, data in list(cluster_state.items()):

        age = now - data.get("last_seen", 0)
        alive = age <= NODE_TTL

        # 🔥 NUEVO: reconciliación de estado
        if not alive and data.get("state") == "ACTIVE":
            data["state"] = "STAND-BY"

    # eliminación real
    to_delete = [
        node_id
        for node_id, data in list(cluster_state.items())
        if (now - data.get("last_seen", 0)) > NODE_TTL
    ]

    for node_id in to_delete:
        print(f"[GC] removing {node_id}")
        del cluster_state[node_id]


def get_active_cluster():
    cleanup_cluster()
    return cluster_state
