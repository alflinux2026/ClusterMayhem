# =========================
# RECONCILER LOOP (SAFE RECOVERY)
# =========================

import time
from cluster.runtime.event_log import load_events
from cluster.runtime.dispatcher import dispatch_created_event
from cluster.runtime.events.event_state import EventStatus


EXECUTION_TIMEOUT = 5.0
CREATED_TIMEOUT = 10.0
MAX_RETRIES = 3


def reconcile_tick():

    now = time.time()

    events = [
        e for e in load_events()
    ]

    for e in events:

        # -------------------------
        # EXECUTING STUCK RECOVERY
        # -------------------------
        if e["status"] == EventStatus.EXECUTING.value:

            if now - e.get("updated_at", e["created_at"]) > EXECUTION_TIMEOUT:

                attempt = e.get("attempt", 0) + 1

                if attempt > MAX_RETRIES:
                    e["status"] = EventStatus.FAILED.value
                    continue

                e["attempt"] = attempt
                e["status"] = EventStatus.CREATED.value

                # re-dispatch SAFE (NO EXECUTING DIRECT)
                dispatch_created_event(e)


        # -------------------------
        # CREATED STUCK RECOVERY
        # -------------------------
        elif e["status"] == EventStatus.CREATED.value:

            if now - e["created_at"] > CREATED_TIMEOUT:

                dispatch_created_event(e)
