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
# BOOT CONTROL (FIXED)
# =========================

BOOT_UNTIL = 0.0
BOOT_LOCK = threading.Lock()

# evita “boot infinito por spam”
MAX_BOOT_SECONDS = 8.0
MIN_BOOT_GAP = 0.5
_last_boot_time = 0.0


def is_booting():
    return time.monotonic() < BOOT_UNTIL


def set_boot(seconds: float):
    global BOOT_UNTIL, _last_boot_time

    now = time.monotonic()

    with BOOT_LOCK:

        # anti-spam: ignora boots demasiado seguidos
        if now - _last_boot_time < MIN_BOOT_GAP:
            return

        _last_boot_time = now

        # CLAMP: nunca permitir boot infinito
        seconds = min(float(seconds), MAX_BOOT_SECONDS)

        # IMPORTANTE:
        # si ya estás en boot, NO lo extiendas agresivamente
        if BOOT_UNTIL > now:
            BOOT_UNTIL = max(BOOT_UNTIL, now + seconds * 0.3)
        else:
            BOOT_UNTIL = now + seconds


# =========================
# FASTAPI
# =========================
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


# =========================
# EXECUTE (bloquea pero NO rompe cluster)
# =========================
@app.post("/execute")
def execute_endpoint(event: ClusterEvent):

    if is_booting():
        return {"error": "booting"}, 503

    return execute_event(event)


# =========================
# ACK (IMPORTANTE: NO bloquear cluster state)
# =========================
@app.post("/ack")
def ack(event: ClusterEvent):

    if is_booting():
        return {"error": "booting"}, 503

    log_state("green", "[ACK]", f"{event.event_id}", 3)
    return {"ok": True, "event_id": event.event_id}


# =========================
# EVENT CORE
# =========================
@app.post("/event")
def event(event: ClusterEvent):

    if is_booting():
        return {"error": "booting"}, 503

    return handle_event(event)


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

            # FIX CRÍTICO: evitar el bug de list/dict
            try:
                return resp.json()
            except Exception:
                return {"error": "invalid response from leader"}

        except Exception as e:
            return {"error": str(e)}

    result = ingest_event(event, ctx.node_id)

    return {
        "status": "ok",
        "event_id": event.event_id,
        "result": result
    }


# =========================
# HEARTBEAT (NO BLOQUEAR DURANTE BOOT)
# =========================
class Heartbeat(BaseModel):
    node_id: str
    state: str
    priority: int


@app.post("/heartbeat")
def heartbeat(hb: Heartbeat):

    # 🔥 IMPORTANTE: NO bloquear heartbeat en boot
    # si no, pierdes cluster_state y nunca hay líder
    cluster_state[hb.node_id] = {
        "state": hb.state,
        "priority": hb.priority,
        "last_seen": time.monotonic(),
    }

    return {"ok": True}


# =========================
# HEALTH (bloquea solo API, no cluster interno)
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


if __name__ == "__main__":

    config = load_or_bootstrap_config()
    run_node(config)
