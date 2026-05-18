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
# BOOT CONTROL (FIXED: NON-STUCK, NON-ACCUMULATIVE)
# =========================================================
BOOT_UNTIL = 0.0
BOOT_LOCK = threading.Lock()


def now():
    return time.time()


def is_booting():
    return now() < BOOT_UNTIL


def set_boot(seconds: float):
    """
    Boot is ABSOLUTE, not cumulative.
    Each call resets window cleanly.
    """
    global BOOT_UNTIL

    seconds = max(0.1, min(float(seconds), 10.0))  # safety cap

    with BOOT_LOCK:
        BOOT_UNTIL = now() + seconds


def boot_remaining():
    return max(0.0, BOOT_UNTIL - now())


# =========================================================
# FASTAPI
# =========================================================
app = FastAPI()


# =========================================================
# CHAOS CONTROL
# =========================================================
@app.post("/boot")
def boot_control(payload: dict):
    seconds = payload.get("seconds", 1.0)
    set_boot(seconds)

    return {
        "ok": True,
        "boot_until": BOOT_UNTIL,
        "remaining": boot_remaining()
    }


@app.get("/debug/boot")
def debug_boot():
    return {
        "now": now(),
        "boot_until": BOOT_UNTIL,
        "remaining": boot_remaining()
    }


# =========================================================
# SAFE RESPONSE WRAPPER
# =========================================================
def boot_error():
    return {"status": "error", "error": "booting"}, 503


# =========================================================
# HEALTH (NEVER BLOCKED)
# =========================================================
@app.get("/health")
def health():
    return {
        "status": "booting" if is_booting() else "ok",
        "node": "alive"
    }


@app.get("/cluster")
def get_cluster():
    return cluster_state


@app.get("/leader")
def get_leader():
    return {"leader": compute_leader()}


# =========================================================
# EXECUTION LAYER (BOOT BLOCKED)
# =========================================================
@app.post("/execute")
def execute_endpoint(event: ClusterEvent):
    if is_booting():
        return boot_error()
    return execute_event(event)


@app.post("/ack")
def ack(event: ClusterEvent):
    if is_booting():
        return boot_error()

    log_state("green", "[ACK]", f"{event.event_id}", 3)
    return {"ok": True, "event_id": event.event_id}


@app.post("/replay")
def replay():
    if is_booting():
        return boot_error()

    replay_events(lambda e: None)
    return {"ok": True}


# =========================================================
# EVENT ENTRYPOINT
# =========================================================
@app.post("/event")
def event(event: ClusterEvent):
    if is_booting():
        return boot_error()

    return handle_event(event)


def handle_event(event: ClusterEvent):

    if is_booting():
        return boot_error()

    leader = compute_leader()

    if not leader:
        return {"status": "error", "error": "no leader"}

    # FORWARD MODE
    if leader != ctx.node_id:

        if is_booting():
            return boot_error()

        log_state("cyan", "[EVENT FWD]", f"{event.event_id} -> {leader}", 3)

        node = CLUSTER_REGISTRY[leader]
        url = f"http://{node['host']}:{node['port']}/event"

        try:
            resp = requests.post(url, json=event.model_dump(), timeout=2)

            # FIX: NEVER assume dict/list → normalize safely
            try:
                return resp.json()
            except Exception:
                return {
                    "status": "error",
                    "error": "invalid_response",
                    "raw": str(resp.text)
                }

        except Exception as e:
            return {"status": "error", "error": str(e)}

    # LEADER PATH
    result = ingest_event(event, ctx.node_id)

    return {
        "status": "ok",
        "event_id": event.event_id,
        "result": result
    }


# =========================================================
# HEARTBEAT (NOT BLOCKED BY BOOT)
# =========================================================
class Heartbeat(BaseModel):
    node_id: str
    state: str
    priority: int


@app.post("/heartbeat")
def heartbeat(hb: Heartbeat):

    cluster_state[hb.node_id] = {
        "state": hb.state,
        "priority": hb.priority,
        "last_seen": now(),
    }

    return {"ok": True}


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
