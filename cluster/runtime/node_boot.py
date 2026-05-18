import threading
import time
import uvicorn
import logging
import requests

from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.responses import FileResponse

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
# STATE GLOBAL
# =========================================================

BOOT_UNTIL = 0.0
BOOT_LOCK = threading.Lock()

NODE_READY = False
NODE_START_TIME = 0.0

BOOT_MAX_SECONDS = 6.0


def is_booting():
    return time.monotonic() < BOOT_UNTIL


def set_boot(seconds: float):
    global BOOT_UNTIL

    now = time.monotonic()

    with BOOT_LOCK:
        seconds = min(float(seconds), BOOT_MAX_SECONDS)
        BOOT_UNTIL = now + seconds


def is_ready():
    return NODE_READY


# =========================================================
# FASTAPI
# =========================================================

app = FastAPI()


@app.post("/boot")
def boot_control(payload: dict):

    seconds = float(payload.get("seconds", 1.0))
    set_boot(seconds)

    return {
        "ok": True,
        "boot_until": BOOT_UNTIL,
        "booting": is_booting()
    }


@app.get("/debug/log")
def log_dump():
    return FileResponse("cluster/data/event_log.local.jsonl")


# =========================================================
# SAFE GUARD
# =========================================================

def guard():
    if not NODE_READY:
        return {"status": "starting"}, 503

    if is_booting():
        return {"error": "booting"}, 503

    return None


# =========================================================
# EXECUTION
# =========================================================

@app.post("/execute")
def execute_endpoint(event: ClusterEvent):

    g = guard()
    if g:
        return g

    return execute_event(event)


@app.post("/ack")
def ack(event: ClusterEvent):

    g = guard()
    if g:
        return g

    log_state("green", "[ACK]", f"{event.event_id}", 3)
    return {"ok": True, "event_id": event.event_id}


# =========================================================
# EVENT SYSTEM
# =========================================================

@app.post("/event")
def event(event: ClusterEvent):

    g = guard()
    if g:
        return g

    return handle_event(event)


def handle_event(event: ClusterEvent):

    leader = compute_leader()

    if not leader:
        return {"error": "no leader"}

    # forward if not leader
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

            try:
                return resp.json()
            except Exception:
                return {"error": "bad leader response"}

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
# HEARTBEAT (IMPORTANT: SOLO CUANDO READY)
# =========================================================

class Heartbeat(BaseModel):
    node_id: str
    state: str
    priority: int


@app.post("/heartbeat")
def heartbeat(hb: Heartbeat):

    if not NODE_READY:
        return {"error": "starting"}, 503

    cluster_state[hb.node_id] = {
        "state": hb.state,
        "priority": hb.priority,
        "last_seen": time.monotonic(),
    }

    return {"ok": True}


# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
def health():

    if not NODE_READY:
        return {"status": "starting"}, 503

    if is_booting():
        return {"status": "booting"}, 503

    return {"status": "ok", "node": ctx.node_id}


@app.get("/cluster")
def get_cluster():
    return cluster_state


@app.get("/leader")
def get_leader():

    if not NODE_READY:
        return {"leader": None, "status": "starting"}

    return {"leader": compute_leader()}


# =========================================================
# WORKER THREAD START
# =========================================================

def start_worker(config):

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


# =========================================================
# BOOTSTRAP SEQUENCE (CRITICAL FIX)
# =========================================================

def run_node(config):

    global NODE_READY, NODE_START_TIME

    ctx.node_id = config["node_id"]

    NODE_START_TIME = time.monotonic()

    start_worker(config)

    # 🔥 FASE 1: dar tiempo a inicialización
    time.sleep(2.0)

    # 🔥 FASE 2: habilitar cluster
    NODE_READY = True

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
