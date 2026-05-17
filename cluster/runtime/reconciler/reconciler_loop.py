# cluster/runtime/reconciler/reconciler_loop.py

import time

from cluster.runtime.events.event_state import EventStatus
from cluster.runtime.events.cluster_event import ClusterEvent
from cluster.runtime.dispatcher import dispatch_created_event
from cluster.runtime.event_log import load_events
from cluster.runtime.leader import compute_leader


EXECUTION_TIMEOUT = 10.0
CREATED_TIMEOUT = 20.0
MAX_RETRIES = 3


def reconcile_tick(node_runtime):

    now = time.time()

    # -----------------------------------------
    # 🔒 GATE 1: solo ACTIVE nodes
    # -----------------------------------------
    if node_runtime.state.value != "ACTIVE":
        return

    # -----------------------------------------
    # 🔒 GATE 2: solo líder real
    # -----------------------------------------
    if compute_leader() != node_runtime.node_id:
        return

    # -----------------------------------------
    # LOAD EVENTS
    # -----------------------------------------
    events = load_events()

    for e in events:

        status = e.get("status")

        # -------------------------
        # TERMINAL STATES
        # -------------------------
        if status in (
            EventStatus.COMPLETED.value,
            EventStatus.FAILED.value
        ):
            continue

        # -------------------------
        # EXECUTING STUCK
        # -------------------------
        if status == EventStatus.EXECUTING.value:

            last_update = e.get("updated_at") or e.get("created_at", now)

            if now - last_update > EXECUTION_TIMEOUT:

                attempt = e.get("attempt", 0) + 1

                if attempt > MAX_RETRIES:
                    e["status"] = EventStatus.FAILED.value
                    continue

                e["attempt"] = attempt
                e["status"] = EventStatus.CREATED.value
                e["updated_at"] = now

                dispatch_created_event(ClusterEvent(**e))

        # -------------------------
        # CREATED STUCK
        # -------------------------
        elif status == EventStatus.CREATED.value:

            created_at = e.get("created_at")

            if created_at and (now - created_at > CREATED_TIMEOUT):

                e["updated_at"] = now
                dispatch_created_event(ClusterEvent(**e))
