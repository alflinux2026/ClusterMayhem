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
from cluster.runtime.worker.event_worker import execute_event

logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("requests").setLevel(logging.ERROR)


# =========================
# BOOT CONTROL (CRITICAL FIX)
# =========================
BOOT_UNTIL = 0
BOOT_LOCK = threading.Lock()


def is_booting():
    return time.time() < BOOT_UNTIL


def set_boot(seconds: float):
    global BOOT_UNTIL
    with BOOT_LOCK:
        BOOT_UNTIL = time.time() + seconds


# =========================
# FASTAPI
# =========================
app = FastAPI()


# -------------------------
# CHAOS CONTROL API
# -------------------------
@app.post("/boot")
def boot_control(payload: dict):
    """
    payload:
      {
        "seconds": 2.5
      }
    """
    seconds = float(payload.get("seconds", 1.0))
    set_boot(seconds)

    return {
        "ok": True,
        "boot_until": BOOT_UNTIL
    }


# -------------------------
# DEBUG LOG
# -------------------------
@app.get("/debug/log")
def log_dump():
    return FileResponse("cluster/data/event_log.local.jsonl")


# -------------------------
# EXECUTE
# -------------------------
@app.post("/execute")
def execute_endpoint(event: ClusterEvent):
    if is_booting():
        return {"error": "booting"}, 503

    return execute_event(event)


# -------------------------
# ACK
# -------------------------
@app.post("/ack")
def ack(event: ClusterEvent):
    if is_booting():
        return {"error": "booting"}, 503

    log_state("green", "[ACK]", f"{event.event_id}", 3)
    return {"ok": True, "event_id": event.event_id}


# -------------------------
# REPLAY
# -------------------------
@app.post("/replay")
def replay():
    if is_booting():
        return {"error": "booting"}, 503

    def handler(event):
        return None

    replay_events(handler)
    return {"ok": True}


# =========================
# EVENT ENTRYPOINT
# =========================
@app.post("/event")
def event(event: ClusterEvent):
    if is_booting():
        return {"error": "booting"}, 503

    return handle_event(event)


def handle_event(event: ClusterEvent):

    if is_booting():
        return {"error": "booting"}, 503

    leader = compute_leader()

    if not leader:
        log_state("red", "(NO LEADER)", event.event_id, 3)
        return {"error": "no leader"}

    # NOT LEADER → forward
    if leader != ctx.node_id:

        if is_booting():
            return {"error": "booting"}, 503

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

    # LEADER → INGEST
    result = ingest_event(event, ctx.node_id)

    return {
        "status": "ok",
        "event_id": event.event_id,
        "result": result
    }


# =========================
# HEARTBEAT
# =========================
class Heartbeat(BaseModel):
    node_id: str
    state: str
    priority: int


@app.post("/heartbeat")
def heartbeat(hb: Heartbeat):

    if is_booting():
        return {"error": "booting"}, 503

    cluster_state[hb.node_id] = {
        "state": hb.state,
        "priority": hb.priority,
        "last_seen": time.time(),
    }

    return {"ok": True}


# =========================
# HEALTH
# =========================
@app.get("/health")
def health():
    if is_booting():
        return {"status": "booting"}, 503

    return {"status": "ok", "node": "alive"}


@app.get("/cluster")
def get_cluster():
    return cluster_state


@app.get("/leader")
def get_leader():
    return {"leader": compute_leader()}


# =========================
# BOOTSTRAP
# =========================
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


# =========================
# ENTRYPOINT
# =========================
if __name__ == "__main__":

    config = load_or_bootstrap_config()
    run_node(config)
