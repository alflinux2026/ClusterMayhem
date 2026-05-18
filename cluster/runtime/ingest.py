from cluster.runtime.event_log import append_event
from cluster.runtime.leader import compute_leader
from cluster.runtime.registry import CLUSTER_REGISTRY
from cluster.utils.log_print import log_state
from cluster.runtime.events.event_state import EventStatus


import requests

def ingest_event(event, node_id):

    # SOLO el leader ejecuta esto
    event.mark_status(EventStatus.CREATED)

    log_state("yellow", "[STATE]", f"{event.event_id} -> EVENT CREATED", 3)

    append_event(event)


    msg = event.payload.get("msg", "<no-msg>")

    log_state(
        "cyan",
        "[EVENT OK]",
        f"{event.event_id} msg={msg}",
        3
    )

    return {
        "event_id": event.event_id,
        "status": "accepted",
        "leader": node_id,
        "trace_id": event.trace_id
    }
