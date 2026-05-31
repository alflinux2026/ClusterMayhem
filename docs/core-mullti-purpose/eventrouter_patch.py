from __future__ import annotations

import requests

from cluster.runtime.registry import CLUSTERREGISTRY
from cluster.utils.logprint import logstate
from cluster.runtime.models import EventEnvelope
from cluster.runtime.eventlog import append_event
from cluster.runtime.events.eventstate import EventStatus


def forwardevent(nodeid: str, event: EventEnvelope):
    node = CLUSTERREGISTRY[nodeid]
    url = f"http://{node.host}:{node.port}/execute"
    event.add_hop(f"forward:{nodeid}")
    logstate("magenta", "WORKER SEND", f"{event.event_id} -> {nodeid}", 3)
    try:
        resp = requests.post(url, json={
            **event.to_record(),
            "stream_id": event.stream.stream_id(),
        }, timeout=2)
        workerresult = resp.json()
    except Exception as e:
        logstate("red", "WORKER SEND FAIL", f"{event.event_id} {e}", 3)
        return {"error": "worker_send_failed"}

    if workerresult.get("status") == "completed":
        event.mark_status(EventStatus.COMPLETED)
        append_event(event)
        logstate("yellow", "EVENT", f"{event.event_id} - COMPLETED", 3)
    return {"status": "forwarded", "event_id": event.event_id, "target": nodeid}
