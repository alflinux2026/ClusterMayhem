from cluster.runtime.cluster_store import cluster_state
import time


def is_alive(data, timeout=1.5):
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




def is_alive_new(data, timeout=1.5):
    return (time.time() - data["last_seen"]) < timeout


def compute_leader_new(debug_node_id=None):

    now = time.time()

    print("\n" + "=" * 60)
    print(f"[LEADER CHECK @ {now:.3f}]")

    active_nodes = {}

    for node_id, data in cluster_state.items():

        age = now - data.get("last_seen", 0)
        alive = is_alive(data)

        print(
            f"- {node_id:10} | "
            f"state={data.get('state'):10} | "
            f"priority={data.get('priority'):3} | "
            f"age={age:6.3f}s | "
            f"alive={alive}"
        )

        if alive:
            active_nodes[node_id] = data

    if not active_nodes:
        print("[LEADER RESULT] None (no active nodes)")
        return None

    leader = min(
        active_nodes.items(),
        key=lambda x: (x[1]["priority"], x[0])
    )[0]

    print(f"[LEADER RESULT] {leader}")
    print("=" * 60 + "\n")

    return leader
