import threading
import time
import uvicorn
import logging
import requests

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from cluster.runtime.cluster_store import cluster_state
from cluster.runtime.node_worker import NodeWorker
from cluster.node.node_runtime import NodeRuntime
from cluster.runtime.leader import compute_leader
from cluster.runtime.bootstrap import load_or_bootstrap_config
from cluster.runtime.registry import CLUSTER_REGISTRY
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


# =========================
# HEARTBEAT
# =========================
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


# =========================
# LEADER DEBUG WRAPPER
# =========================
def debug_compute_leader(tag=""):
    leader = compute_leader()
    log_state("magenta", "[LEADER]", f"{tag} leader={leader}", 2)
    return leader


# =========================
# EVENT ENTRYPOINT
# =========================
@app.post("/event")
def handle_event(event: ClusterEvent):

    leader = debug_compute_leader(event.event_id)

    if not leader:
        log_state("red", "[NO LEADER]", event.event_id, 3)
        return {"error": "no leader"}

    # forward if not local leader
    if leader != ctx.node_id:

        log_state(
            "cyan",
            "[EVENT FWD]",
            f"{event.event_id} -> {leader}",
            3
        )

        node = CLUSTER_REGISTRY.get(leader)

        if not node:
            return {"error": "leader not found"}

        try:
            resp = requests.post(
                f"http://{node['host']}:{node['port']}/event",
                json=event.model_dump(),
                timeout=2
            )
            return resp.json()

        except Exception as e:
            return {"error": str(e)}

    # leader executes
    result = ingest_event(event, ctx.node_id)

    return {
        "status": "ok",
        "event_id": event.event_id,
        "result": result
    }


# =========================
# SIMPLE DEBUG
# =========================
@app.get("/cluster")
def get_cluster():
    return cluster_state


@app.get("/leader")
def get_leader():
    return {"leader": compute_leader()}


@app.get("/health")
def health():
    return {"status": "ok", "node": ctx.node_id}


# =========================
# BOOTSTRAP
# =========================
def run_node(config):

    ctx.node_id = config["node_id"]
    ctx.priority = config["priority"]

    # register immediately (CRÍTICO)
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

    threading.Thread(target=worker.start, daemon=True).start()

    # =========================
    # INITIAL HEARTBEAT (FIX CLAVE)
    # =========================
    def initial_heartbeat():
        time.sleep(0.3)

        try:
            requests.post(
                f"http://127.0.0.1:{config.get('bind_port', 7000)}/heartbeat",
                json={
                    "node_id": ctx.node_id,
                    "state": "alive",
                    "priority": ctx.priority,
                },
                timeout=1
            )
        except Exception as e:
            print("[BOOT HEARTBEAT FAIL]", e)

    threading.Thread(target=initial_heartbeat, daemon=True).start()

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
