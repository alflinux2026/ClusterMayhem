from cluster.runtime.event_log import append_event
from cluster.runtime.leader import compute_leader
from cluster.runtime.registry import CLUSTER_REGISTRY
from cluster.utils.log_print import log_state

import requests

def ingest_event(event, node_id):

    # SOLO el leader ejecuta esto
    event.status = "created"

    append_event(event)


    log_state(
                "cyan",
                "[EVENT OK]",
                f"{event.event_id} event_type={event.event_type}",
                3
            )

    return {
        "event_id": event.event_id,
        "status": "accepted",
        "leader": node_id,
        "trace_id": event.trace_id
    }
