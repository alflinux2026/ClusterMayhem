import time
import requests

from cluster.runtime.cluster_store import cluster_state
from cluster.runtime.registry import CLUSTER_REGISTRY
from cluster.runtime.leader import compute_leader
from cluster.utils.log_print import log_state

from cluster.runtime.events.cluster_event import ClusterEvent
from cluster.runtime.event_log import (
    append_event,
    get_completed_event_ids,
)

from cluster.runtime.events.event_state import EventStatus



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

    event.add_hop("leader_routed")

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
    event.mark_status(EventStatus.EXECUTING)

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

        event.mark_status(EventStatus.COMPLETED)

        requests.post(
            ack_url,
            json=event.model_dump(),
            timeout=2
        )



