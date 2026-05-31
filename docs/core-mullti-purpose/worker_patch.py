from __future__ import annotations

from cluster.runtime.eventlog import append_event
from cluster.runtime.models import EventEnvelope, EventStatus
from cluster.utils.logprint import logstate

executedkeys: set[str] = set()


def runbusinesslogic(payload: dict) -> dict:
    return {"ok": True, "payload": payload}


def executeevent(event: EventEnvelope):
    event.execution_key = f"{event.event_id}:{event.attempt}"
    if event.execution_key in executedkeys:
        logstate("red", "CACHE HIT", event.execution_key, 3)
        return {"status": "completed", "cached": True, "event_id": event.event_id, "execution_key": event.execution_key}
    result = runbusinesslogic(event.payload)
    executedkeys.add(event.execution_key)
    event.mark_status(EventStatus.COMPLETED)
    append_event(event)
    return {"status": "completed", "event_id": event.event_id, "execution_key": event.execution_key, "result": result}
