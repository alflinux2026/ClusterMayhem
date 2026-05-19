
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

#    log_state("yellow", "[DISPATCH]", f"event={event.event_id} start", 3)

    # -------------------------
    # avoid duplicate completion
    # -------------------------
    completed = get_completed_event_ids()
    if event.event_id in completed:
        log_state("red", "[SKIP COMPLETED]", event.event_id, 3)
        return

    # -------------------------
    # select target
    # -------------------------
    alive = {
        node_id_: data
        for node_id_, data in cluster_state.items()
        if (time.time() - data["last_seen"]) < 3.0
    }

 #   log_state("cyan", "[ALIVE]", str(list(alive.keys())), 3)

    if not alive:
        log_state("red", "[NO ALIVE NODES]", event.event_id, 3)
        return

  #  log_state("yellow", "[DISPATCH]", f"event={event.event_id}", 3)
  #  log_state("cyan", "[ALIVE]", str(list(alive.keys())), 3)


    # calculo identico de worker que de leader
    target = min(
        alive.items(),
        key=lambda x: (x[1]["priority"], x[0])
    )[0]

   # log_state("magenta", "[WORKER SELECTED]", target, 3)

   # log_state("magenta", "[WORKER SELECTED]", f"{event.event_id} -> {target}", 3)

    # -------------------------
    # ROUTING METADATA
    # -------------------------
    event.target_node = target
    event.route_hops.append(f"dispatcher->{target}")

    #log_state("magenta", "[ROUTE]", f"{event.event_id} hop added", 3)

    # -------------------------
    # STATE CHANGE
    # -------------------------

    event.attempt = (event.attempt or 0) + 1   # 👈 AQUI
    event.attempt = 0

    event.mark_status(EventStatus.EXECUTING)


    msg = event.payload.get("msg", "<no-msg>")

    log_state("yellow", "(EVENT)", f"{msg:12} -> EVENT EXECUTING", 3)

    # -------------------------
    # PERSIST
    # -------------------------
    event.updated_at = time.time()
    append_event(event)

    #log_state("green", "[PERSIST]", event.event_id, 3)

#    log_state("magenta", "[DISPATCH SEND]", f"{event.event_id} -> {target}", 3)

    # -------------------------
    # SEND
    # -------------------------
#    log_state("magenta", "[SEND]", f"{event.event_id} -> {target}", 3)

    forward_event(target, event)
