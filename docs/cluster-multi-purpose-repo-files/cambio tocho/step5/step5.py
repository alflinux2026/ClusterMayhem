from pathlib import Path
out = Path('output')
out.mkdir(exist_ok=True)

patches = {
'cluster_runtime_dispatcher_stream_patch.py': '''import time

from cluster.runtime.event_log import get_created_events, get_completed_event_ids, append_event
from cluster.runtime.event_router import forward_event
from cluster.utils.log_print import log_state
from cluster.runtime.leader import compute_leader, compute_alive
from cluster.runtime import context as ctx
from cluster.runtime.events.event_state import EventStatus

DISPATCH_ALIVE_TIMEOUT = 1.5


def dispatch_tick(stream=None):
    if compute_leader() != ctx.node_id:
        return
    events = get_created_events(stream)
    if not events:
        return
    log_state("magenta", "[DISPATCH]", f"{len(events):3}", 3)
    for event in events:
        dispatch_created_event(event, stream)


def dispatch_created_event(event, stream=None):
    completed = get_completed_event_ids(stream)
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
    forward_event(target, event, stream)
''',
'cluster_runtime_reconciler_stream_patch.py': '''import time
from collections import defaultdict

from cluster.runtime.event_log import load_events, append_event
from cluster.runtime.events.cluster_event import ClusterEvent
from cluster.runtime.events.event_state import EventStatus

EXECUTION_TIMEOUT = 10.0


def reconcile_tick(node_runtime, stream=None):
    if node_runtime.state != node_runtime.state.__class__.ACTIVE:
        return

    events = load_events(stream)
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
''',
'cluster_runtime_worker_event_worker_stream_patch.py': '''from cluster.runtime.event_log import append_event
from cluster.runtime.events.event_state import EventStatus
from cluster.utils.log_print import log_state

executed_keys = set()


def run_business_logic(payload: dict):
    return {"ok": True, "payload": payload}


def execute_event(event, stream=None):
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
''',
'cluster_runtime_event_router_stream_patch.py': '''import requests

from cluster.runtime.registry import CLUSTER_REGISTRY
from cluster.utils.log_print import log_state
from cluster.runtime.events.cluster_event import ClusterEvent
from cluster.runtime.event_log import append_event
from cluster.runtime.events.event_state import EventStatus


def forward_event(node_id: str, event: ClusterEvent, stream=None):
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
''',
'cluster_runtime_api_app_stream_patch.py': '''import os
import time
import logging
import requests

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from cluster.runtime.cluster_store import cluster_state
from cluster.runtime.leader import compute_leader
from cluster.runtime.registry import CLUSTER_REGISTRY
from cluster.runtime.event_log import (
    replay_events,
    get_local_log_path,
    get_replica_log_path,
    write_replica_log,
)
from cluster.runtime.ingest import ingest_event
from cluster.runtime.events.cluster_event import ClusterEvent
from cluster.runtime import context as ctx
from cluster.utils.log_print import log_state
from cluster.runtime.worker.event_worker import execute_event
from cluster.runtime.node_runtime import NodeState
from cluster.runtime.integrity import local_integrity_api, cluster_integrity_report, canonicalize
from cluster.runtime.models import StreamKey


logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("requests").setLevel(logging.ERROR)

app = FastAPI()


class Heartbeat(BaseModel):
    node_id: str
    state: str
    priority: int
    log_meta: dict | None = None
    cluster_integrity: dict | None = None
    streams: dict | None = None


@app.get("/debug/log")
def log_dump():
    path = get_local_log_path()
    if not os.path.exists(path):
        return PlainTextResponse("", status_code=200)
    return FileResponse(path, media_type="text/plain")


@app.get("/debug/log/local")
def log_dump_local():
    path = get_local_log_path()
    if not os.path.exists(path):
        return PlainTextResponse("", status_code=200)
    return FileResponse(path, media_type="text/plain")


@app.get("/debug/log/replica/{node_id}")
def log_dump_replica(node_id: str):
    path = get_replica_log_path(node_id)
    if not os.path.exists(path):
        return PlainTextResponse("", status_code=404)
    return FileResponse(path, media_type="text/plain")


@app.post("/debug/log/replica/{node_id}")
async def log_replica_write(node_id: str, request: Request):
    content = await request.body()
    text = content.decode("utf-8") if content else ""
    write_replica_log(node_id, text)
    return {"ok": True, "node_id": node_id, "path": get_replica_log_path(node_id), "bytes": len(content)}


@app.post("/execute")
def execute_endpoint(event: ClusterEvent):
    if ctx.node.state == NodeState.ISOLATED:
        return {"error": "node isolated"}
    return execute_event(event)


@app.post("/ack")
def ack(event: ClusterEvent):
    log_state("green", "[ACK]", f"{event.event_id} received", 3)
    return {"ok": True, "event_id": event.event_id}


@app.post("/replay")
def replay():
    def handler(event):
        return None
    replay_events(handler)
    return {"ok": True}


@app.post("/event")
def handle_event(event: ClusterEvent):
    if ctx.node.state == NodeState.ISOLATED:
        return {"error": "node isolated"}

    leader = compute_leader()
    if not leader:
        log_state("red", "(NO LEADER)", event.event_id, 3)
        return {"error": "no leader"}

    if leader != ctx.node_id:
        msg = event.payload.get("msg", "<no-msg>")
        log_state("cyan", "[EVENT FWD]", f"{msg:12} -> {leader}", 3)
        node = CLUSTER_REGISTRY[leader]
        url = f"http://{node['host']}:{node['port']}/event"
        try:
            resp = requests.post(url, json=event.model_dump(), timeout=2)
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    result = ingest_event(event, ctx.node_id)
    return {"status": "ok", "event_id": event.event_id, "result": result}


@app.post("/sleep")
def sleep():
    log_state("red", "- SLEEP -", f"{ctx.node_id} -> SLEEP", 3)
    ctx.node.transition(NodeState.ISOLATED)
    return {"ok": True, "node": ctx.node_id, "state": ctx.node.state.value}


@app.post("/revive")
def revive():
    log_state("red", "- WAKEUP -", f"{ctx.node_id} -> WAKEUP", 3)
    ctx.node.transition(NodeState.STANDBY)
    return {"ok": True, "node": ctx.node_id, "state": ctx.node.state.value}


@app.get("/health")
def health():
    return {"status": "ok", "node": ctx.node_id, "sleeping": ctx.node.state == NodeState.ISOLATED}


@app.get("/cluster")
def get_cluster():
    return cluster_state


@app.get("/leader")
def get_leader():
    return {"leader": compute_leader()}


@app.post("/heartbeat")
def heartbeat(hb: Heartbeat):
    if ctx.node.state == NodeState.ISOLATED:
        return {"error": "node isolated"}

    existing = cluster_state.get(hb.node_id, {})
    cluster_state[hb.node_id] = {
        "state": hb.state,
        "priority": hb.priority,
        "last_seen": time.time(),
        "log_meta": hb.log_meta or {},
        "cluster_integrity": hb.cluster_integrity or existing.get("cluster_integrity", {}),
        "streams": hb.streams or existing.get("streams", {}),
    }

    return {"ok": True}


@app.get("/integrity")
def integrity():
    return local_integrity_api()


@app.get("/integrity/cluster")
def integrity_cluster():
    return cluster_integrity_report()
'''
}

for name, content in patches.items():
    (out / name).write_text(content, encoding='utf-8')

print('stream pipeline patches ready')
