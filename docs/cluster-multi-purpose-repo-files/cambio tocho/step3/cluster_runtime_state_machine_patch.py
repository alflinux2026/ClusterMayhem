from cluster.runtime.events.event_state import EventStatus, validate_transition
from cluster.runtime.event_log import load_events, append_event
from cluster.runtime.events.cluster_event import ClusterEvent


def transition_event(event_id: str, new_status: EventStatus):
    events = load_events()
    latest = None
    for raw in reversed(events):
        if raw.get("event_id") == event_id:
            latest = raw
            break
    if not latest:
        return {"error": "event_not_found", "event_id": event_id}

    current_status = latest.get("status")
    if hasattr(current_status, "value"):
        current_status = current_status.value

    if not validate_transition(EventStatus(current_status), new_status):
        return {"error": "invalid_transition", "from": current_status, "to": new_status.value}

    updated = dict(latest)
    updated["status"] = new_status.value
    updated["updated_at"] = __import__('time').time()
    event = ClusterEvent(**updated)
    append_event(event)
    return {"ok": True, "event_id": event_id, "status": new_status.value}
