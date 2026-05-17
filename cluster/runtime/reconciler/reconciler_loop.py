import time

from cluster.runtime.events.event_state import EventStatus
from cluster.runtime.events.cluster_event import ClusterEvent
from cluster.runtime.dispatcher import dispatch_created_event
from cluster.runtime.event_log import load_events, append_event


EXECUTION_TIMEOUT = 10.0
CREATED_TIMEOUT = 20.0
MAX_RETRIES = 3
REQUEUE_COOLDOWN = 5.0


def reconcile_tick(node_runtime):

    # 🔒 ONLY ACTIVE NODE
    if node_runtime.state != node_runtime.state.__class__.ACTIVE:
        return

    now = time.time()

    events = load_events()

    for e in events:

        status = e.get("status")

        # skip terminal states
        if status in (
            EventStatus.COMPLETED.value,
            EventStatus.FAILED.value
        ):
            continue

        # -------------------------------------------------
        # EXECUTING STUCK
        # -------------------------------------------------
        if status == EventStatus.EXECUTING.value:

            last_update = e.get("updated_at") or e.get("created_at", now)

            if now - last_update > EXECUTION_TIMEOUT:

                attempt = e.get("attempt", 0) + 1

                if attempt > MAX_RETRIES:
                    e["status"] = EventStatus.FAILED.value
                    e["updated_at"] = now
                    append_event(ClusterEvent(**e))
                    continue

                e["attempt"] = attempt
                e["status"] = EventStatus.CREATED.value
                e["updated_at"] = now

                append_event(ClusterEvent(**e))

                dispatch_created_event(ClusterEvent(**e))

        # -------------------------------------------------
        # CREATED STUCK
        # -------------------------------------------------
        elif status == EventStatus.CREATED.value:

            created_at = e.get("created_at", 0)
            last_update = e.get("updated_at", 0)

            # 🧠 cooldown anti-loop
            if now - last_update < REQUEUE_COOLDOWN:
                continue

            if now - created_at > CREATED_TIMEOUT:

                e["updated_at"] = now

                append_event(ClusterEvent(**e))
                dispatch_created_event(ClusterEvent(**e))
