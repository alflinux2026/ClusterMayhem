import time
import requests

from cluster.runtime.cluster_store import cluster_state
from cluster.runtime.registry import CLUSTER_REGISTRY
from cluster.runtime.leader import compute_leader
from cluster.utils.log_print import log_state

from cluster.runtime.events.cluster_event import ClusterEvent

from cluster.runtime.event_log import append_event



# =========================
# FORWARD TO LEADER
# =========================
def forward_to_leader(event: ClusterEvent):

    leader = compute_leader()

    if not leader:
        log_state("red", "(NO LEADER)", event.event_id, 3)
        return {"error": "no leader"}

    node = CLUSTER_REGISTRY[leader]
    url = f"http://{node['host']}:{node['port']}/route"

    event.add_hop("forward_to_leader")
    event.mark_status("routed")

    resp = requests.post(
        url,
        json=event.model_dump(),
        timeout=2
    )

    try:
        return resp.json()
    except:
        return {"status": "forwarded", "raw": resp.text}


# =========================
# FORWARD TO WORKER
# =========================
def forward_event(node_id: str, event: ClusterEvent):

    node = CLUSTER_REGISTRY[node_id]
    url = f"http://{node['host']}:{node['port']}/execute"

    event.add_hop(f"worker:{node_id}")
    event.mark_status("executing")

    log_state("magenta", "[WORKER SEND]", f"{event.event_id} -> {node_id}", 3)

    requests.post(
        url,
        json=event.model_dump(),
        timeout=2
    )

    # -------------------------
    # ACK TO LEADER
    # -------------------------

    leader = compute_leader()

    if leader:

        leader_node = CLUSTER_REGISTRY[leader]

        ack_url = (
            f"http://{leader_node['host']}:"
            f"{leader_node['port']}/ack"
        )

        event.mark_status("completed")

        requests.post(
            ack_url,
            json=event.model_dump(),
            timeout=2
        )




def route_event(event: ClusterEvent):

    # -------------------------
    # IDEMPOTENCY
    # -------------------------
#    from cluster.runtime.event_log import get_completed_event_ids

    completed = get_completed_event_ids()

    if event.event_id in completed:

        log_state(
            "yellow",
            "(SKIP DUP)",
            event.event_id,
            3
        )

        return {
            "skipped": True,
            "event_id": event.event_id
        }

    # 🔥 PERSISTENCIA REAL (SOLO LEADER WORKFLOW)
    append_event(event)

    # -------------------------
    # FILTER ALIVE NODES
    # -------------------------
    alive = {
        node_id: data
        for node_id, data in cluster_state.items()
        if (time.time() - data["last_seen"]) < 3.0
    }

    if not alive:
        log_state("red", "(NO WORKERS)", event.event_id, 3)
        event.mark_status("failed")
        return {"error": "no alive nodes"}

    log_state("magenta", "(ALIVE)", f"{list(alive.keys())}", 3)

    # -------------------------
    # WORKER SELECTION
    # -------------------------
    target = max(
        alive.items(),
        key=lambda x: (x[1]["priority"], x[0])
    )[0]

    log_state("magenta", "(WORKER)", f"selected={target}", 3)

    event.add_hop(f"router->worker:{target}")
    event.target_node = target
    event.mark_status("executing")

    # -------------------------
    # PERSIST LEADER DECISION
    # -------------------------
    from cluster.runtime.event_log import append_event
    append_event(event)

    # -------------------------
    # EXECUTE
    # -------------------------
    forward_event(target, event)

    return {
        "routed_to": target,
        "event_id": event.event_id,
        "trace_id": event.trace_id
    }
