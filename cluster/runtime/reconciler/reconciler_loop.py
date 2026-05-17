import time
from collections import defaultdict

from cluster.runtime.event_log import load_events, append_event
from cluster.runtime.events.cluster_event import ClusterEvent
from cluster.runtime.events.event_state import EventStatus


EXECUTION_TIMEOUT = 10.0


def reconcile_tick(node_runtime):

    # SOLO nodo activo
    if node_runtime.state != node_runtime.state.__class__.ACTIVE:
        return

    events = load_events()
    now = time.time()

    # -----------------------------------------
    # 1. AGRUPAR POR EVENT_ID
    # -----------------------------------------
    by_id = defaultdict(list)

    for e in events:
        eid = e.get("event_id")
        if not eid:
            continue
        by_id[eid].append(e)

    print("\n\n================ RECONCILER DEBUG ================\n")

    # -----------------------------------------
    # 2. PROCESAR CADA EVENTO
    # -----------------------------------------
    for eid, history in by_id.items():

        history.sort(key=lambda x: (
            x.get("updated_at") or x.get("created_at") or 0
        ))

        print(f"\nEVENT_ID: {eid}")
        print("-" * 60)

        for i, h in enumerate(history):

            ts = h.get("updated_at") or h.get("created_at") or 0
            status = h.get("status")
            node = h.get("target_node")
            attempt = h.get("attempt")

            print(
                f"[{i}] "
                f"ts={ts:.3f} "
                f"status={status:<10} "
                f"node={node} "
                f"attempt={attempt}"
            )

        latest = history[-1]
        latest_status = latest.get("status")

        print("\n→ LATEST:", latest_status)

        # -----------------------------------------
        # 🔧 OPCIÓN 1: RECOVERY DE EXECUTING STUCK
        # -----------------------------------------
        if latest_status == EventStatus.EXECUTING.value:

            last_update = latest.get("updated_at") or latest.get("created_at", 0)

            if now - last_update > EXECUTION_TIMEOUT:

                print(f"⚠️ RECOVERY: EXECUTING STUCK -> CREATED ({eid})")

                recovered = dict(latest)
                recovered["status"] = EventStatus.CREATED.value
                recovered["updated_at"] = now
                recovered.pop("owner", None)

                append_event(ClusterEvent(**recovered))

        print("-" * 60)

    print("\n==================================================\n")
