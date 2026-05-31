from pathlib import Path
out = Path('output')
out.mkdir(exist_ok=True)

dispatcher = '''import time

from cluster.runtime.event_log import get_created_events, get_completed_event_ids, append_event
from cluster.runtime.event_router import forward_event
from cluster.utils.log_print import log_state
from cluster.runtime.leader import compute_leader, compute_alive
from cluster.runtime import context as ctx
from cluster.runtime.events.event_state import EventStatus

DISPATCH_ALIVE_TIMEOUT = 1.5


def dispatch_tick():
    if compute_leader() != ctx.node_id:
        return
    events = get_created_events()
    if not events:
        return
    log_state("magenta", "[DISPATCH]", f"{len(events):3}", 3)
    for event in events:
        dispatch_created_event(event)


def dispatch_created_event(event):
    completed = get_completed_event_ids()
    if event.event_id in completed:
        log_state("red", "[SKIP COMPLETED]", event.event_id, 3)
        return
    alive = compute_alive(timeout=DISPATCH_ALIVE_TIMEOUT, include_self=True)
    if not alive:
        log_state("red", "[NO ALIVE NODES]", event.event_id, 3)
        return
    target = min(alive.items(), key=lambda x: (x[1]["priority"], x[0]))[0]
    event.target_node = target
    event.route_hops.append(f"dispatcher->{target}")
    event.attempt = (event.attempt or 0) + 1
    event.mark_status(EventStatus.EXECUTING)
    msg = event.payload.get("msg", "")
    log_state("yellow", "(EVENT)", f"{msg:12} -> EXECUTING", 3)
    event.updated_at = time.time()
    append_event(event)
    forward_event(target, event)
'''

worker = '''from cluster.runtime.event_log import append_event
from cluster.runtime.events.event_state import EventStatus
from cluster.utils.log_print import log_state

executed_keys = set()


def run_business_logic(payload: dict):
    return {"ok": True, "payload": payload}


def execute_event(event):
    event.execution_key = f"{event.event_id}:{event.attempt}"

    if event.execution_key in executed_keys:
        log_state("red", "[CACHE HIT]", event.execution_key, 3)
        return {
            "status": "completed",
            "cached": True,
            "event_id": event.event_id,
            "execution_key": event.execution_key,
        }

    result = run_business_logic(event.payload)
    executed_keys.add(event.execution_key)

    msg = event.payload.get("msg", "<no-msg>")
    log_state("green", "[EXECUTE]", f"{msg:12}", 3)

    event.mark_status(EventStatus.COMPLETED)
    append_event(event)

    return {
        "status": "completed",
        "event_id": event.event_id,
        "execution_key": event.execution_key,
        "result": result,
    }
'''

event_router = '''import requests

from cluster.runtime.registry import CLUSTER_REGISTRY
from cluster.utils.log_print import log_state
from cluster.runtime.events.cluster_event import ClusterEvent
from cluster.runtime.event_log import append_event
from cluster.runtime.events.event_state import EventStatus


def forward_event(node_id: str, event: ClusterEvent):
    node = CLUSTER_REGISTRY[node_id]
    url = f"http://{node['host']}:{node['port']}/execute"

    event.add_hop(f"worker:{node_id}")

    msg = event.payload.get("msg", "<no-msg>")

    log_state("magenta", "[WORKER SEND]", f"{msg:12} -> {node_id}", 3)

    try:
        resp = requests.post(
            url,
            json=event.model_dump(),
            timeout=2,
        )
        worker_result = resp.json()
    except Exception as e:
        log_state("red", "[WORKER SEND FAIL]", f"{msg:12} -> {node_id} | {e}", 3)
        return {"error": "worker_send_failed"}

    if worker_result.get("status") == "completed":
        event.mark_status(EventStatus.COMPLETED)
        append_event(event)
        log_state("yellow", "(EVENT)", f"{msg:12} -> COMPLETED", 3)

    return {
        "status": "forwarded",
        "event_id": event.event_id,
        "target": node_id,
    }
'''

reconciler = '''import time
from collections import defaultdict

from cluster.runtime.event_log import load_events, append_event
from cluster.runtime.events.cluster_event import ClusterEvent
from cluster.runtime.events.event_state import EventStatus


EXECUTION_TIMEOUT = 10.0


def reconcile_tick(node_runtime):
    if node_runtime.state != node_runtime.state.__class__.ACTIVE:
        return

    events = load_events()
    now = time.time()

    by_id = defaultdict(list)
    for e in events:
        eid = e.get("event_id")
        if not eid:
            continue
        by_id[eid].append(e)

    incomplete = False
    for history in by_id.values():
        latest_status = history[-1].get("status")
        if latest_status not in (EventStatus.COMPLETED.value, EventStatus.FAILED.value):
            incomplete = True
            break

    if not incomplete:
        return

    print("\n\n================ RECONCILER DEBUG ================\n")

    for eid, history in by_id.items():
        history.sort(key=lambda x: (x.get("updated_at") or x.get("created_at") or 0))
        latest = history[-1]
        latest_status = latest.get("status")

        if latest_status in (EventStatus.COMPLETED.value, EventStatus.FAILED.value):
            continue

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

        print("\n→ LATEST:", latest_status)

        if latest_status == EventStatus.EXECUTING.value:
            last_update = latest.get("updated_at") or latest.get("created_at", 0)

            if now - last_update > EXECUTION_TIMEOUT:
                print(f"⚠ RECOVERY: EXECUTING STUCK -> CREATED ({eid})")

                recovered = dict(latest)
                recovered["status"] = EventStatus.CREATED.value
                recovered["updated_at"] = now
                recovered["target_node"] = None
                recovered["execution_key"] = None
                recovered["attempt"] = 0
                recovered["route_hops"] = []
                recovered.pop("owner", None)

                append_event(ClusterEvent(**recovered))

        print("-" * 60)

    print("\n==================================================\n")
'''

files = {
    'cluster_runtime_dispatcher_patch.py': dispatcher,
    'cluster_runtime_worker_patch.py': worker,
    'cluster_runtime_event_router_patch.py': event_router,
    'cluster_runtime_reconciler_patch.py': reconciler,
}
for name, content in files.items():
    (out / name).write_text(content, encoding='utf-8')

print('dispatcher/worker/router/reconciler patches ready')
