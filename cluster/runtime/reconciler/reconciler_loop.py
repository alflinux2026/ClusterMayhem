import time

from cluster.runtime.event_log import load_events
from cluster.runtime.dispatcher import dispatch_created_event
from cluster.runtime.events.event_state import EventStatus
from cluster.runtime.events.cluster_event import ClusterEvent


EXECUTION_TIMEOUT = 10.0
CREATED_TIMEOUT = 20.0
MAX_RETRIES = 3


def reconcile_tick():

    now = time.time()

    events = load_events()

    for e in events:

        if e["status"] == EventStatus.COMPLETED.value:
            continue

        if e["status"] == EventStatus.FAILED.value:
            continue

        # -------------------------
        # EXECUTING STUCK
        # -------------------------
        if e["status"] == EventStatus.EXECUTING.value:

            last_update = e.get("updated_at") or e.get("created_at", now)

            if now - last_update > EXECUTION_TIMEOUT:

                attempt = e.get("attempt", 0) + 1

                if attempt > MAX_RETRIES:
                    e["status"] = EventStatus.FAILED.value
                    continue

                e["attempt"] = attempt
                e["status"] = EventStatus.CREATED.value

                dispatch_created_event(ClusterEvent(**e))

        # -------------------------
        # CREATED STUCK
        # -------------------------
        elif e["status"] == EventStatus.CREATED.value:

            created_at = e.get("created_at", now)

            if now - created_at > CREATED_TIMEOUT:

                dispatch_created_event(ClusterEvent(**e))
