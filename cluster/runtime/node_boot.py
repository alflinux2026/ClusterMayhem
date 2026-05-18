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
# NODE STATES (NEW)
# =====================================================

STATE_BOOT = "BOOT"
STATE_ACTIVE = "ACTIVE"
STATE_SLEEP = "SLEEP"

def is_leader_eligible(node_id: str) -> bool:
    state = cluster_state.get(node_id, {}).get("state")
    return state == STATE_ACTIVE


# =====================================================
# FASTAPI
# =====================================================

app = FastAPI()


@app.get("/debug/log")
def log_dump():
    return FileResponse("cluster/data/event_log.local.jsonl")


@app.post("/execute")
def execute_endpoint(event: ClusterEvent):
    return ingest_event(event, ctx.node_id)


@app.post("/ack")
def ack(event: ClusterEvent):
    log_state("green", "[ACK]", event.event_id, 3)
    return {"ok": True}


@app.post("/replay")
def replay():
    def handler(event):
        return None

    replay_events(handler)
    return {"ok": True}


# =====================================================
# LEADER RESOLUTION (FIX HERE)
# =====================================================

def get_valid_leader():
    leader = debug_compute_leader(event.event_id)

    if not leader:
        return None

    if not is_leader_eligible(leader):
        return None

    return leader


# =====================================================
# EVENT FLOW
# =====================================================

@app.post("/event")
def handle_event(event: ClusterEvent):

    leader = get_valid_leader()

    if not leader:
        log_state("red", "(NO LEADER)", event.event_id, 3)
        return {"error": "no leader"}

    # -----------------------------------
    # NOT LEADER → forward
    # -----------------------------------

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

    # -----------------------------------
    # LEADER → INGEST
    # -----------------------------------

    result = ingest_event(event, ctx.node_id)

    return {
        "status": "ok",
        "event_id": event.event_id,
        "result": result
    }


# =====================================================
# CLUSTER METADATA
# =====================================================

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


# =====================================================
# CONTROL (NEW IMPORTANT PART)
# =====================================================

@app.post("/sleep")
def sleep():
    cluster_state[ctx.node_id] = {
        "state": STATE_SLEEP,
        "priority": ctx.priority,
        "last_seen": time.time(),
    }
    log_state("red", "(SLEEP)", ctx.node_id, 3)
    return {"ok": True}


@app.post("/wake")
def wake():
    cluster_state[ctx.node_id] = {
        "state": STATE_ACTIVE,
        "priority": ctx.priority,
        "last_seen": time.time(),
    }
    log_state("green", "(WAKE)", ctx.node_id, 3)
    return {"ok": True}


# =====================================================
# BOOTSTRAP
# =====================================================

def run_node(config):

    ctx.node_id = config["node_id"]
    ctx.priority = config["priority"]

    # BOOT STATE (NOT LEADER ELIGIBLE INITIALLY)
    cluster_state[ctx.node_id] = {
        "state": STATE_BOOT,
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

    # auto transition BOOT → ACTIVE
    def boot_transition():
        time.sleep(2)
        cluster_state[ctx.node_id]["state"] = STATE_ACTIVE
        log_state("green", "(BOOT -> ACTIVE)", ctx.node_id, 3)

    threading.Thread(target=boot_transition, daemon=True).start()

    uvicorn.run(
        app,
        host=config.get("bind_host", "0.0.0.0"),
        port=config.get("bind_port", 7000),
        log_level="warning",
        access_log=False
    )


def debug_compute_leader(tag: str = ""):
    leader = compute_leader()

    log_state(
        "magenta",
        "[LEADER DEBUG]",
        f"{tag} leader={leader} node={ctx.node_id}",
        2
    )

    return leader

# =====================================================
# ENTRYPOINT
# =====================================================

if __name__ == "__main__":

    config = load_or_bootstrap_config()
    run_node(config)
