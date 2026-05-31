import requests

from cluster.runtime.registry import CLUSTER_REGISTRY
from cluster.utils.log_print import log_state
from cluster.runtime.events.cluster_event import ClusterEvent
from cluster.runtime.event_log import append_event
from cluster.runtime.events.event_state import EventStatus


def forward_event(node_id: str, event: ClusterEvent):
    node = CLUSTER_REGISTRY[node_id]
    url = f"http://{node['host']}:{node['port']}/execute"

    event.add_hop(f"worker:{node_id}")

    msg = event.payload.get("msg", "<no-msg>")

    log_state("magenta", "[WORKER SEND]", f"{msg:12} -> {node_id}", 3)

    try:
        resp = requests.post(
            url,
            json=event.model_dump(),
            timeout=2,
        )
        worker_result = resp.json()
    except Exception as e:
        log_state("red", "[WORKER SEND FAIL]", f"{msg:12} -> {node_id} | {e}", 3)
        return {"error": "worker_send_failed"}

    if worker_result.get("status") == "completed":
        event.mark_status(EventStatus.COMPLETED)
        append_event(event)
        log_state("yellow", "(EVENT)", f"{msg:12} -> COMPLETED", 3)

    return {
        "status": "forwarded",
        "event_id": event.event_id,
        "target": node_id,
    }
