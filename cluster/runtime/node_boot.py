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


# =========================
# FASTAPI
# =========================
app = FastAPI()


@app.get("/debug/log")
def log_dump():
    return FileResponse("cluster/data/event_log.local.jsonl")


@app.post("/execute")
def execute_endpoint(event: ClusterEvent):
    return ingest_event(event, ctx.node_id)


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


# =========================
# LEADER FLOW
# =========================
@app.post("/event")
def handle_event(event: ClusterEvent):

    leader = compute_leader()

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


# =========================
# METADATA
# =========================
class Heartbeat(BaseModel):
    node_id: str
    state: str
    priority: int


@app.get("/health")
def health():
    return {"status": "ok", "node": ctx.node_id}


@app.get("/cluster")
def get_cluster():
    return cluster_state


@app.get("/leader")
def get_leader():
    return {"leader": compute_leader()}


@app.post("/heartbeat")
def heartbeat(hb: Heartbeat):
    cluster_state[hb.node_id] = {
        "state": hb.state,
        "priority": hb.priority,
        "last_seen": time.time(),
    }
    return {"ok": True}


# =========================
# BOOTSTRAP FIX (CRÍTICO)
# =========================
def run_node(config):

    ctx.node_id = config["node_id"]
    ctx.priority = config["priority"]

    # ✅ IMPORTANTE: NO usar BOOT como estado que bloquea election
    # directamente ACTIVE desde el inicio
    cluster_state[ctx.node_id] = {
        "state": "ACTIVE",   # 🔥 FIX PRINCIPAL
        "priority": ctx.priority,
        "last_seen": time.time(),
    }

    log_state("green", "(BOOT -> ACTIVE)", ctx.node_id, 3)

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


# =========================
# ENTRYPOINT
# =========================
if __name__ == "__main__":

    config = load_or_bootstrap_config()
    run_node(config)
