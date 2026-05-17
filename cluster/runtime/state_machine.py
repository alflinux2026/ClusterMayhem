# runtime/state_machine.py

from cluster.runtime.events.event_state import EventStatus, validate_transition
from cluster.runtime.event_log import load_events, append_event


def transition_event(event_id: str, new_status: EventStatus):

    events = load_events()

    latest = None
    for e in reversed(events):
        if e["event_id"] == event_id:
            latest = e
            break

    if not latest:
        return

    old_status = latest["status"]

    validate_transition(EventStatus(old_status), new_status)

    latest["status"] = new_status

    append_event(latest)
