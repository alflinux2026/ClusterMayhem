# runtime/state_machine.py

from cluster.runtime.events.event_state import EventStatus, validate_transition
from cluster.runtime.event_log import load_events, append_event

from cluster.runtime.events.cluster_event import ClusterEvent

def transition_event(event_id: str, new_status):

    events = load_events()

    latest_raw = None

    for e in reversed(events):
        if e["event_id"] == event_id:
            latest_raw = e
            break

    if not latest_raw:
        return

    latest = ClusterEvent(**latest_raw)  # 🔥 NORMALIZACIÓN AQUÍ

    old_status = latest.status

    validate_transition(old_status, new_status)

    latest.status = new_status

    append_event(latest)  # ✔ ahora sí correcto
