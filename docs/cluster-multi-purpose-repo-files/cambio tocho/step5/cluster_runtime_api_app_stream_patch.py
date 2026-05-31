import os
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
