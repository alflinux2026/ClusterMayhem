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

    node = CLUSTER_REGISTRY[node_id]
    url = f"http://{node['host']}:{node['port']}/execute"

    event.add_hop(f"worker:{node_id}")

    msg = event.payload.get("msg", "<no-msg>")

    log_state(
        "magenta",
        "[WORKER SEND]",
        f"{msg:12} -> {node_id}",
        3
    )

    # -------------------------
    # SEND TO WORKER
    # -------------------------
    try:

        #log_state("red", "[BEFORE POST]", url, 3)
        resp = requests.post(
            url,
            json=event.model_dump(),
            timeout=2
        )
        #log_state("red", "[AFTER POST]", str(resp.status_code), 3)


        worker_result = resp.json()

    except Exception as e:
        log_state(
            "red",
            "[WORKER SEND FAIL]",
            f"{msg:12} -> {node_id} | {e}",
            3
        )
        return {"error": "worker_send_failed"}

    # -------------------------
    # LEADER DECIDES FINAL STATE (Opción B real)
    # -------------------------
    if worker_result.get("status") == "completed":

        from cluster.runtime.state_machine import transition_event
        from cluster.runtime.events.event_state import EventStatus

        transition_event(
            event.event_id,
            EventStatus.COMPLETED
        )


        log_state(
            "yellow",
            "(EVENT)",
            f"{msg:12} -> EVENT COMPLETED",
            3
        )

    return {
        "status": "forwarded",
        "event_id": event.event_id,
        "target": node_id
    }
