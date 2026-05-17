import time
from collections import defaultdict

from cluster.runtime.event_log import load_events


def reconcile_tick(node_runtime):

    # SOLO nodo activo
    if node_runtime.state != node_runtime.state.__class__.ACTIVE:
        return

    events = load_events()

    # -----------------------------------------
    # 1. AGRUPAR POR EVENT_ID
    # -----------------------------------------
    by_id = defaultdict(list)

    for e in events:
        eid = e.get("event_id")   # ✔ FIX IMPORTANTE
        if not eid:
            continue
        by_id[eid].append(e)

    now = time.time()

    print("\n\n================ RECONCILER DEBUG ================\n")

    # -----------------------------------------
    # 2. PROCESAR CADA EVENTO
    # -----------------------------------------
    for eid, history in by_id.items():

        # ordenar por tiempo real de evento
        history.sort(key=lambda x: (
            x.get("updated_at") or x.get("created_at") or 0
        ))

        print(f"\nEVENT_ID: {eid}")
        print("-" * 60)

        for i, h in enumerate(history):

            ts = h.get("updated_at") or h.get("created_at")
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
        print("\n→ LATEST:", latest.get("status"))

        # separación visual
        print("-" * 60)

    print("\n==================================================\n")
