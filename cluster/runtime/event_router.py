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
# FORWARD TO WORKER (TRANSPORT ONLY)
# =========================

import requests

from cluster.runtime.registry import CLUSTER_REGISTRY
from cluster.runtime.leader import compute_leader
from cluster.utils.log_print import log_state
from cluster.runtime.events.cluster_event import ClusterEvent


def forward_event(node_id: str, event: ClusterEvent):

    # -------------------------
    # BUILD TARGET URL
    # -------------------------
    node = CLUSTER_REGISTRY[node_id]
    url = f"http://{node['host']}:{node['port']}/execute"

    # -------------------------
    # TRACE ONLY (NO STATE CHANGE)
    # -------------------------
    event.add_hop(f"worker:{node_id}")

    # -------------------------
    # LOG TRANSPORT
    # -------------------------
    log_state(
        "magenta",
        "[WORKER SEND]",
        f"{event.event_id} -> {node_id}",
        3
    )

    # -------------------------
    # SEND TO WORKER
    # -------------------------
    try:
        resp = requests.post(
            ack_url,
            json=event.model_dump(),
            timeout=2
        )

        if resp.status_code == 200: {
            transition_event(event.event_id, EventStatus.COMPLETED)
            log_state("yellow", "[STATE]", f"{event.event_id} -> EVENT COMPLETED", 3)
        }

    except Exception as e:
        log_state(
            "red",
            "[WORKER SEND FAIL]",
            f"{event.event_id} -> {node_id} | {e}",
            3
        )
        return {"error": "worker_send_failed"}

    # -------------------------
    # ACK TO LEADER (TRANSPORT ONLY)
    # -------------------------
    leader = compute_leader()

    if not leader:
        return {"error": "no_leader"}

    leader_node = CLUSTER_REGISTRY[leader]

    ack_url = (
        f"http://{leader_node['host']}:"
        f"{leader_node['port']}/ack"
    )

    try:
        requests.post(
            ack_url,
            json=event.model_dump(),
            timeout=2
        )
    except Exception as e:
        log_state(
            "red",
            "[ACK FAIL]",
            f"{event.event_id} | {e}",
            3
        )
        return {"error": "ack_failed"}

    # -------------------------
    # IMPORTANT:
    # NO STATE CHANGES HERE
    # -------------------------
    return {
        "status": "forwarded",
        "event_id": event.event_id,
        "target": node_id
    }
