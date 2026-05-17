
import time

from cluster.runtime.event_log import (
    get_created_events,
    get_completed_event_ids,
    append_event,
)

from cluster.runtime.cluster_store import cluster_state
from cluster.runtime.event_router import forward_event

from cluster.utils.log_print import log_state
from cluster.runtime.leader import compute_leader
#from cluster.runtime.node_boot import node_id
from cluster.runtime import context as ctx

from cluster.runtime.events.event_state import EventStatus


# =========================
# DISPATCH LOOP (LEADER ONLY)
# =========================

def dispatch_tick():

    # ONLY LEADER EXECUTES DISPATCH
    if compute_leader() != ctx.node_id:
        return

    events = get_created_events()

    if not events:
        return

    log_state(
        "magenta",
        "[DISPATCH]",
        f"pending={len(events)}",
        3
    )

    for event in events:
        dispatch_created_event(event)


# =========================
# DISPATCH SINGLE EVENT
# =========================

def dispatch_created_event(event):

    # avoid duplicate completion
    completed = get_completed_event_ids()
    if event.event_id in completed:
        return

    # select target
    alive = {
        node_id_: data
        for node_id_, data in cluster_state.items()
        if (time.time() - data["last_seen"]) < 3.0
    }

    if not alive:
        return

    target = max(
        alive.items(),
        key=lambda x: (x[1]["priority"], x[0])
    )[0]

    # -------------------------
    # ROUTING METADATA
    # -------------------------
    event["target_node"] = target
    event.setdefault("route_hops", []).append(f"dispatcher->{target}")

    # -------------------------
    # STATE CHANGE (ONLY HERE)
    # -------------------------
    event["status"] = EventStatus.EXECUTING.value

    # -------------------------
    # PERSIST BEFORE SEND (CRITICAL)
    # -------------------------
    append_event(event)

    # -------------------------
    # SEND TO WORKER
    # -------------------------
    forward_event(target, event)
