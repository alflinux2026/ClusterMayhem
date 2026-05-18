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
# BOOT CONTROL (FIXED: safer + auto-release fallback)
# =========================================================
BOOT_UNTIL = 0
BOOT_LOCK = threading.Lock()

BOOT_DEFAULT_SECONDS = 3.0  # safety net: NEVER infinite boot


def is_booting():
    return time.time() < BOOT_UNTIL


def set_boot(seconds: float):
    global BOOT_UNTIL
    with BOOT_LOCK:
        BOOT_UNTIL = time.time() + seconds


def auto_boot_release():
    """Failsafe: ensures node NEVER stays in boot forever"""
    global BOOT_UNTIL
    while True:
        time.sleep(1.0)
        with BOOT_LOCK:
            if BOOT_UNTIL == 0:
                BOOT_UNTIL = time.time() + BOOT_DEFAULT_SECONDS
            elif time.time() > BOOT_UNTIL + 10:
                # hard escape if something went wrong
                BOOT_UNTIL = time.time() - 1


threading.Thread(target=auto_boot_release, daemon=True).start()

# =========================================================
# FASTAPI
# =========================================================
app = FastAPI()


# =========================================================
# CHAOS CONTROL
# =========================================================
@app.post("/boot")
def boot_control(payload: dict):
    seconds = float(payload.get("seconds", BOOT_DEFAULT_SECONDS))
    set_boot(seconds)
    return {"ok": True, "boot_until": BOOT_UNTIL}


# =========================================================
# HEALTH (IMPORTANT: NEVER BLOCKED COMPLETELY)
# =========================================================
@app.get("/health")
def health():
    # allow health even in boot → cluster can recover
    return {
        "status": "booting" if is_booting() else "ok",
        "node": ctx.node_id
    }


# =========================================================
# HEARTBEAT (CRITICAL FIX: NEVER BLOCK THIS)
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
        "last_seen": time.time(),
    }
    return {"ok": True}


# =========================================================
# EXECUTE
# =========================================================
@app.post("/execute")
def execute_endpoint(event: ClusterEvent):
    if is_booting():
        return {"error": "booting"}, 503
    return execute_event(event)


# =========================================================
# ACK
# =========================================================
@app.post("/ack")
def ack(event: ClusterEvent):
    if is_booting():
        return {"error": "booting"}, 503

    log_state("green", "[ACK]", event.event_id, 3)
    return {"ok": True, "event_id": event.event_id}


# =========================================================
# EVENT ENTRYPOINT
# =========================================================
@app.post("/event")
def event(event: ClusterEvent):
    if is_booting():
        return {"error": "booting"}, 503
    return handle_event(event)


def handle_event(event: ClusterEvent):
    leader = compute_leader()

    # FIX: empty cluster fallback → SELF becomes leader
    if not leader:
        leader = ctx.node_id

    # forward if not leader
    if leader != ctx.node_id:

        log_state("cyan", "[EVENT FWD]", f"{event.event_id} -> {leader}", 3)

        node = CLUSTER_REGISTRY.get(leader)
        if not node:
            return {"error": "leader not found"}

        url = f"http://{node['host']}:{node['port']}/event"

        try:
            resp = requests.post(
                url,
                json=event.model_dump(),
                timeout=3
            )

            # =========================
            # FIX CRITICAL BUG HERE
            # =========================
            try:
                data = resp.json()
                if isinstance(data, list):
                    return {"status": "error", "error": "invalid list response"}
                return data
            except Exception:
                return {"status": "error", "error": "bad json response"}

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
# REPLAY
# =========================================================
@app.post("/replay")
def replay():
    if is_booting():
        return {"error": "booting"}, 503

    def handler(event):
        return None

    replay_events(handler)
    return {"ok": True}


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

    # IMPORTANT FIX:
    # ensure node exits boot after startup
    set_boot(BOOT_DEFAULT_SECONDS)

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
