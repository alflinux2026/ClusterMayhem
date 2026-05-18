import threading
import time
import uvicorn
import logging
import requests

from fastapi.responses import FileResponse
from fastapi import FastAPI
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

logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("requests").setLevel(logging.ERROR)


# =====================================================
# FASTAPI
# =====================================================
app = FastAPI()


# =====================================================
# DEBUG: ver líder en cada request (CLAVE)
# =====================================================
def debug_leader(tag=""):
    leader = compute_leader()
    print(f"[LEADER DEBUG] {tag} node={ctx.node_id} leader={leader} state={cluster_state}")
    return leader


# =====================================================
# EVENT FLOW
# =====================================================
@app.post("/event")
def handle_event(event: ClusterEvent):

    leader = debug_leader(event.event_id)

    if not leader:
        log_state("red", "(NO LEADER)", event.event_id, 3)
        return {"error": "no leader"}

    if leader != ctx.node_id:

        log_state("cyan", "[EVENT FWD]", f"{event.event_id} -> {leader}", 3)

        node = CLUSTER_REGISTRY[leader]
        url = f"http://{node['host']}:{node['port']}/event"

        try:
            resp = requests.post(
                url,
                json=event.model_dump(),
                timeout=2
            )
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    result = ingest_event(event, ctx.node_id)

    return {
        "status": "ok",
        "event_id": event.event_id,
        "result": result
    }


# =====================================================
# HEALTH
# =====================================================
class Heartbeat(BaseModel):
    node_id: str
    state: str
    priority: int


@app.post("/heartbeat")
def heartbeat(hb: Heartbeat):

    cluster_state[hb.node_id] = {
        "state": hb.state,
        "priority": hb.priority,
        "last_seen": time.time(),
    }

    return {"ok": True}


# =====================================================
# 🔥 FIX CRÍTICO: SLEEP / REVIVE REAL
# =====================================================

@app.post("/sleep")
def sleep():

    cluster_state[ctx.node_id] = {
        "state": "SLEEP",
        "priority": ctx.priority,
        "last_seen": time.time(),
    }

    print(f"[SLEEP] {ctx.node_id} -> SLEEP")

    return {"ok": True}


@app.post("/revive")
def revive():

    cluster_state[ctx.node_id] = {
        "state": "STANDBY",
        "priority": ctx.priority,
        "last_seen": time.time(),
    }

    print(f"[REVIVE] {ctx.node_id} -> STANDBY")

    return {"ok": True}


# =====================================================
# HEALTH
# =====================================================
@app.get("/cluster")
def get_cluster():
    return cluster_state


@app.get("/leader")
def get_leader():
    return {"leader": compute_leader()}


@app.get("/health")
def health():
    return {"status": "ok", "node": ctx.node_id}


# =====================================================
# BOOTSTRAP (SIN CAMBIOS)
# =====================================================
def run_node(config):

    ctx.node_id = config["node_id"]
    ctx.priority = config["priority"]

    cluster_state[ctx.node_id] = {
        "state": "STANDBY",
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

    threading.Thread(target=worker.start, daemon=True).start()

    uvicorn.run(
        app,
        host=config.get("bind_host", "0.0.0.0"),
        port=config.get("bind_port", 7000),
        log_level="warning",
        access_log=False
    )


# =====================================================
# ENTRYPOINT
# =====================================================
if __name__ == "__main__":

    config = load_or_bootstrap_config()
    run_node(config)
