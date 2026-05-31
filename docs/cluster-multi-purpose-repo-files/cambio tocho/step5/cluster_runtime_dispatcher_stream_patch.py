import time

from cluster.runtime.event_log import get_created_events, get_completed_event_ids, append_event
from cluster.runtime.event_router import forward_event
from cluster.utils.log_print import log_state
from cluster.runtime.leader import compute_leader, compute_alive
from cluster.runtime import context as ctx
from cluster.runtime.events.event_state import EventStatus

DISPATCH_ALIVE_TIMEOUT = 1.5


def dispatch_tick(stream=None):
    if compute_leader() != ctx.node_id:
        return
    events = get_created_events(stream)
    if not events:
        return
    log_state("magenta", "[DISPATCH]", f"{len(events):3}", 3)
    for event in events:
        dispatch_created_event(event, stream)


def dispatch_created_event(event, stream=None):
    completed = get_completed_event_ids(stream)
    if event.event_id in completed:
        log_state("red", "[SKIP COMPLETED]", event.event_id, 3)
        return
    alive = compute_alive(timeout=DISPATCH_ALIVE_TIMEOUT, include_self=True)
    if not alive:
        log_state("red", "[NO ALIVE NODES]", event.event_id, 3)
        return
    target = min(alive.items(), key=lambda x: (x[1]["priority"], x[0]))[0]
    event.target_node = target
    event.route_hops.append(f"dispatcher->{target}")
    event.attempt = (event.attempt or 0) + 1
    event.mark_status(EventStatus.EXECUTING)
    msg = event.payload.get("msg", "")
    log_state("yellow", "(EVENT)", f"{msg:12} -> EXECUTING", 3)
    event.updated_at = time.time()
    append_event(event)
    forward_event(target, event, stream)
