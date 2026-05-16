from cluster.runtime.event_log import append_event
from cluster.runtime.leader import compute_leader
from cluster.runtime.registry import CLUSTER_REGISTRY
import requests

def ingest_event(event, node_id):

    # SOLO el leader ejecuta esto
    event.status = "created"

    append_event(event)

    return {
        "event_id": event.event_id,
        "status": "accepted",
        "leader": node_id,
        "trace_id": event.trace_id
    }
