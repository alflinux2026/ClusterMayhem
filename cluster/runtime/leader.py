from cluster.utils.log_print import log_state
from cluster.runtime.cluster_store import cluster_state
import time


def is_alive(data, timeout=1.5):
    return (time.time() - data["last_seen"]) < timeout


def compute_leader(debug_node_id=None):

    now = time.time()


    active_nodes = {}

    for node_id, data in cluster_state.items():

        age = now - data.get("last_seen", 0)
        alive = is_alive(data)


#        log_state("blue", "[NODE]", f"| {node_id:10} | {data.get('state'):8} | " \
#            f"{data.get('priority'):1} | {age:6.3f}s | {alive}", 3)

        # if data.get('state') == '  GONE  ':
        #   time.sleep(30)




        if alive:
            active_nodes[node_id] = data

        else:
            data['state'] = '  GONE  '   # 👈 aquí lo marcas aunque esté muerto


#    log_state("blue", "[NODE]", f"---------------------------------------------------", 3)

    if not active_nodes:
        return None

    leader = min(
        active_nodes.items(),
        key=lambda x: (x[1]["priority"], x[0])
    )[0]


    return leader
