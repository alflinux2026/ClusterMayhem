import time
from collections import defaultdict

from cluster.runtime.events.event_state import EventStatus
from cluster.runtime.events.cluster_event import ClusterEvent
from cluster.runtime.dispatcher import dispatch_created_event
from cluster.runtime.event_log import load_events, append_event


EXECUTION_TIMEOUT = 10.0
CREATED_TIMEOUT = 20.0
MAX_RETRIES = 3
REQUEUE_COOLDOWN = 5.0


def reconcile_tick(node_runtime):

    if node_runtime.state != node_runtime.state.__class__.ACTIVE:
        return

    now = time.time()
    events = load_events()

    # -------------------------------------------------
    # 1. MATERIALIZE LATEST STATE PER EVENT
    # -------------------------------------------------
    latest = {}

    for e in events:
        eid = e.get("id")
        if not eid:
            continue

        # keep last occurrence (append-only log)
        if eid not in latest or e.get("updated_at", 0) > latest[eid].get("updated_at", 0):
            latest[eid] = e

    # -------------------------------------------------
    # 2. RECONCILE ONLY CURRENT STATE
    # -------------------------------------------------
    for eid, e in latest.items():

        status = e.get("status")

        # terminal states → ignore
        if status in (EventStatus.COMPLETED.value, EventStatus.FAILED.value):
            continue

        # -------------------------------------------------
        # EXECUTING WATCHDOG
        # -------------------------------------------------
        if status == EventStatus.EXECUTING.value:

            last_update = e.get("updated_at") or e.get("created_at", now)

            if now - last_update <= EXECUTION_TIMEOUT:
                continue

            attempt = e.get("attempt", 0) + 1

            if attempt > MAX_RETRIES:
                e["status"] = EventStatus.FAILED.value
                e["updated_at"] = now
                append_event(ClusterEvent(**e))
                continue

            e["attempt"] = attempt
            e["status"] = EventStatus.CREATED.value
            e["updated_at"] = now
            e.pop("owner", None)

            append_event(ClusterEvent(**e))
            continue

        # -------------------------------------------------
        # CREATED → DISPATCH CONTROLLED
        # -------------------------------------------------
        if status == EventStatus.CREATED.value:

            created_at = e.get("created_at", 0)
            last_update = e.get("updated_at", 0)

            if now - last_update < REQUEUE_COOLDOWN:
                continue

            if now - created_at < CREATED_TIMEOUT:
                continue

            # CLAIM (soft lock)
            e["status"] = EventStatus.EXECUTING.value
            e["owner"] = node_runtime.node_id
            e["updated_at"] = now

            append_event(ClusterEvent(**e))
            dispatch_created_event(ClusterEvent(**e))
