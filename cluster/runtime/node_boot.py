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
# NODE FAILURE STATE (REAL KILL / REVIVE)
# =========================================================

NODE_DEAD = False
NODE_LOCK = threading.Lock()


def kill_node():
    global NODE_DEAD

    with NODE_LOCK:
        NODE_DEAD = True

        cluster_state[ctx.node_id] = {
            "state": "dead",
            "priority": ctx.priority,
            "last_seen": time.time(),
        }

        log_state("red", "(TIME TO SLEEP)", ctx.node_id, 3)


def revive_node():
    global NODE_DEAD

    with NODE_LOCK:
        NODE_DEAD = False

        cluster_state[ctx.node_id] = {
            "state": "alive",
            "priority": ctx.priority,
            "last_seen": time.time(),
        }

        log_state("red", "(TIME TO WAKE UP)", ctx.node_id, 3)


def is_dead():
    with NODE_LOCK:
        return NODE_DEAD


# =========================================================
# FASTAPI
# =========================================================

app = FastAPI()


# =========================================================
# HARD KILL MIDDLEWARE
# =========================================================

@app.middleware("http")
async def death_middleware(request: Request, call_next):

    # endpoints permitidos incluso muerto
    ALWAYS_ALLOWED = {
        "/health",
        "/revive",
        "/kill",
    }

    if request.url.path in ALWAYS_ALLOWED:
        return await call_next(request)

    # blackout total
    if is_dead():
        return Response(
            status_code=503,
            content='{"error":"node_dead"}',
            media_type="application/json"
        )

    return await call_next(request)


# =========================================================
# CONTROL API
# =========================================================

@app.post("/kill")
def kill():
    kill_node()
    return {"ok": True, "state": "dead"}


@app.post("/revive")
def revive():
    revive_node()
    return {"ok": True, "state": "alive"}


# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
def health():

    return {
        "status": "dead" if is_dead() else "alive",
        "node": ctx.node_id,
    }


# =========================================================
# SAFE LEADER
# =========================================================

def compute_leader_safe():

    # limpia nodos muertos por timeout
    now = time.time()

    for node_id, state in list(cluster_state.items()):

        last_seen = state.get("last_seen", 0)

        if now - last_seen > 5:
            state["state"] = "dead"

    leader = compute_leader()

    if not leader:
        return None

    leader_state = cluster_state.get(leader)

    if not leader_state:
        return None

    if leader_state.get("state") != "alive":
        return None

    return leader


# =========================================================
# EVENT FLOW
# =========================================================

@app.post("/event")
def event(event: ClusterEvent):
    return handle_event(event)


def handle_event(event: ClusterEvent):

    if is_dead():
        return {"status": "error", "error": "node_dead"}

    # =====================================================
    # LEADER RESOLUTION
    # =====================================================

    leader = compute_leader()

    # líder inválido si está marcado dead
    if leader:

        leader_state = cluster_state.get(leader)

        if not leader_state or leader_state.get("state") != "alive":
            leader = None

    if not leader:

        log_state("yellow", "[NO LEADER]", event.event_id, 3)

        return {
            "status": "error",
            "error": "no leader"
        }

    # =====================================================
    # FORWARD TO LEADER
    # =====================================================

    if leader != ctx.node_id:

        log_state(
            "cyan",
            "[EVENT FWD]",
            f"{event.event_id} -> {leader}",
            3
        )

        node = CLUSTER_REGISTRY.get(leader)

        if not node:
            return {
                "status": "error",
                "error": "leader not found"
            }

        url = f"http://{node['host']}:{node['port']}/event"

        try:

            resp = requests.post(
                url,
                json=event.model_dump(),
                timeout=3
            )

            # nodo muerto
            if resp.status_code >= 500:

                return {
                    "status": "error",
                    "error": "leader unavailable"
                }

            try:
                data = resp.json()

                # FIX CRÍTICO
                if isinstance(data, list):
                    return {
                        "status": "error",
                        "error": "invalid response format"
                    }

                return data

            except Exception:

                return {
                    "status": "error",
                    "error": "bad json response"
                }

        except Exception as e:

            return {
                "status": "error",
                "error": str(e)
            }

    # =====================================================
    # LEADER INGEST
    # =====================================================

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

    if is_dead():
        return {"status": "error", "error": "node_dead"}

    return execute_event(event)


# =========================================================
# ACK
# =========================================================

@app.post("/ack")
def ack(event: ClusterEvent):

    if is_dead():
        return {"status": "error", "error": "node_dead"}

    log_state("green", "[ACK]", event.event_id, 3)

    return {
        "ok": True,
        "event_id": event.event_id
    }


# =========================================================
# HEARTBEAT
# =========================================================

class Heartbeat(BaseModel):
    node_id: str
    state: str
    priority: int



@app.post("/heartbeat")
def heartbeat(hb: Heartbeat):

    # nodo local muerto -> ignorar heartbeats propios
    if hb.node_id == ctx.node_id and is_dead():
        return {"ignored": True}

    existing = cluster_state.get(hb.node_id)

    # no revivir nodos muertos automáticamente
    if existing and existing.get("state") == "dead":
        return {"ignored": True}

    cluster_state[hb.node_id] = {
        "state": "alive",
        "priority": hb.priority,
        "last_seen": time.time(),
    }

    return {"ok": True}




# =========================================================
# DEBUG
# =========================================================

@app.get("/debug/log")
def log_dump():
    return FileResponse("cluster/data/event_log.local.jsonl")


# =========================================================
# REPLAY
# =========================================================

@app.post("/replay")
def replay():

    if is_dead():
        return {"status": "error", "error": "node_dead"}

    def handler(event):
        return None

    replay_events(handler)

    return {"ok": True}


# =========================================================
# BOOT
# =========================================================

def run_node(config):

    ctx.node_id = config["node_id"]
    ctx.priority = config["priority"]

    # self register alive
    cluster_state[ctx.node_id] = {
        "state": "alive",
        "priority": ctx.priority,
        "last_seen": time.time(),
    }

    node = NodeRuntime(
        node_id=config["node_id"],
        priority=config["priority"],
    )

    worker = NodeWorker(
        node=node,
        peers=config["peers"],
        interval=1.0
    )

    threading.Thread(
        target=worker.start,
        daemon=True
    ).start()

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
