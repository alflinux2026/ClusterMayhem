import threading
import time
import uvicorn
import logging
import requests

from fastapi import FastAPI, Request
from fastapi.responses import Response, FileResponse
from pydantic import BaseModel

from cluster.runtime.cluster_store import cluster_state
from cluster.runtime.node_worker import NodeWorker
from cluster.node.node_runtime import NodeRuntime
from cluster.runtime.leader import compute_leader
from cluster.runtime.bootstrap import load_or_bootstrap_config
from cluster.runtime.registry import CLUSTER_REGISTRY
from cluster.runtime.event_log import replay_events
from cluster.runtime.ingest import ingest_event
from cluster.runtime.events.cluster_event import ClusterEvent
from cluster.runtime import context as ctx
from cluster.utils.log_print import log_state
from cluster.runtime.worker.event_worker import execute_event

logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("requests").setLevel(logging.ERROR)

# =========================================================
# NODE FAILURE STATE (REAL "DEAD NODE" SIMULATION)
# =========================================================
NODE_DEAD = False
NODE_LOCK = threading.Lock()


def kill_node():
    global NODE_DEAD
    with NODE_LOCK:
        NODE_DEAD = True


def revive_node():
    global NODE_DEAD
    with NODE_LOCK:
        NODE_DEAD = False


def is_dead():
    return NODE_DEAD


# =========================================================
# FASTAPI
# =========================================================
app = FastAPI()


# =========================================================
# GLOBAL DEATH MIDDLEWARE (CORE FIX)
# =========================================================
@app.middleware("http")
async def death_middleware(request: Request, call_next):

    # allow health ALWAYS (important for cluster recovery)
    if request.url.path == "/health":
        return await call_next(request)

    if is_dead():
        return Response(
            status_code=503,
            content='{"error":"node_dead"}',
            media_type="application/json"
        )

    return await call_next(request)


# =========================================================
# CHAOS CONTROL API
# =========================================================
@app.post("/kill")
def kill(payload: dict = None):
    kill_node()
    return {"ok": True, "state": "dead"}


@app.post("/revive")
def revive(payload: dict = None):
    revive_node()
    return {"ok": True, "state": "alive"}


# =========================================================
# HEALTH (IMPORTANT: ALWAYS AVAILABLE)
# =========================================================
@app.get("/health")
def health():
    return {
        "status": "dead" if is_dead() else "alive",
        "node": ctx.node_id
    }


# =========================================================
# HEARTBEAT (still works unless you want full blackout)
# =========================================================
class Heartbeat(BaseModel):
    node_id: str
    state: str
    priority: int


@app.post("/heartbeat")
def heartbeat(hb: Heartbeat):

    # even dead nodes can optionally stop heartbeat
    if is_dead():
        return {"error": "node_dead"}, 503

    cluster_state[hb.node_id] = {
        "state": hb.state,
        "priority": hb.priority,
        "last_seen": time.time(),
    }

    return {"ok": True}


# =========================================================
# EVENT FLOW
# =========================================================
@app.post("/event")
def event(event: ClusterEvent):
    return handle_event(event)


def handle_event(event: ClusterEvent):

    leader = compute_leader()

    if not leader:
        leader = ctx.node_id

    if leader != ctx.node_id:

        log_state("cyan", "[EVENT FWD]", f"{event.event_id} -> {leader}", 3)

        node = CLUSTER_REGISTRY.get(leader)
        if not node:
            return {"error": "leader not found"}

        url = f"http://{node['host']}:{node['port']}/event"

        try:
            resp = requests.post(url, json=event.model_dump(), timeout=3)

            try:
                data = resp.json()
                if isinstance(data, list):
                    return {"error": "invalid response format"}
                return data
            except Exception:
                return {"error": "bad response"}

        except Exception as e:
            return {"error": str(e)}

    # leader path
    result = ingest_event(event, ctx.node_id)

    return {
        "status": "ok",
        "event_id": event.event_id,
        "result": result
    }


# =========================================================
# EXECUTE
# =========================================================
@app.post("/execute")
def execute_endpoint(event: ClusterEvent):
    return execute_event(event)


# =========================================================
# ACK
# =========================================================
@app.post("/ack")
def ack(event: ClusterEvent):
    log_state("green", "[ACK]", event.event_id, 3)
    return {"ok": True, "event_id": event.event_id}


# =========================================================
# DEBUG LOG
# =========================================================
@app.get("/debug/log")
def log_dump():
    return FileResponse("cluster/data/event_log.local.jsonl")


# =========================================================
# BOOTSTRAP
# =========================================================
def run_node(config):

    ctx.node_id = config["node_id"]

    node = NodeRuntime(
        node_id=config["node_id"],
        priority=config["priority"],
    )

    worker = NodeWorker(
        node=node,
        peers=config["peers"],
        interval=1.0
    )

    threading.Thread(target=worker.start, daemon=True).start()

    uvicorn.run(
        app,
        host=config.get("bind_host", "0.0.0.0"),
        port=config.get("bind_port", 7000),
        log_level="warning",
        access_log=False
    )


# =========================================================
# ENTRYPOINT
# =========================================================
if __name__ == "__main__":
    config = load_or_bootstrap_config()
    run_node(config)
