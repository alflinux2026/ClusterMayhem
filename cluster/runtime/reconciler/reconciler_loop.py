import time

from cluster.runtime.event_log import load_events
from cluster.runtime.dispatcher import dispatch_created_event
from cluster.runtime.events.event_state import EventStatus
from cluster.runtime.events.cluster_event import ClusterEvent

from cluster.runtime.node_state import get_node_state, NodeState
from cluster.runtime.leader_election import is_leader


EXECUTION_TIMEOUT = 10.0
CREATED_TIMEOUT = 20.0
MAX_RETRIES = 3


def reconcile_tick():

    # -----------------------------------------
    # 🔒 GLOBAL GATE: ONLY ACTIVE LEADER RUNS
    # -----------------------------------------
    if get_node_state() != NodeState.ACTIVE:
        return

    if not is_leader():
        return

    now = time.time()

    events = load_events()

    for e in events:

        status = e.get("status")

        # -----------------------------------------
        # SKIP FINAL STATES
        # -----------------------------------------
        if status in (
            EventStatus.COMPLETED.value,
            EventStatus.FAILED.value
        ):
            continue

        # -----------------------------------------
        # EXECUTING STUCK RECOVERY
        # -----------------------------------------
        if status == EventStatus.EXECUTING.value:

            last_update = e.get("updated_at") or e.get("created_at", now)

            if now - last_update > EXECUTION_TIMEOUT:

                attempt = e.get("attempt", 0) + 1

                if attempt > MAX_RETRIES:
                    e["status"] = EventStatus.FAILED.value
                    continue

                # rollback to CREATED safely
                e["attempt"] = attempt
                e["status"] = EventStatus.CREATED.value

                try:
                    dispatch_created_event(ClusterEvent(**e))
                except Exception as ex:
                    # evita crash del reconciler
                    print(f"[RECONCILER ERROR] dispatch failed: {ex}")

        # -----------------------------------------
        # CREATED STUCK RE-DISPATCH (IDEMPOTENT SAFE)
        # -----------------------------------------
        elif status == EventStatus.CREATED.value:

            created_at = e.get("created_at")

            if not created_at:
                continue

            if now - created_at > CREATED_TIMEOUT:

                try:
                    dispatch_created_event(ClusterEvent(**e))
                except Exception as ex:
                    print(f"[RECONCILER ERROR] re-dispatch failed: {ex}")
