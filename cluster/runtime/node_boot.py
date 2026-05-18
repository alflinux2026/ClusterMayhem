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


HB_LOCK = threading.Lock()


# =====================================================
# FASTAPI
# =====================================================
app = FastAPI()

# =====================================================
# LOCAL SLEEP STATE (NO CLUSTER TOUCH)
# =====================================================
NODE_SLEEP = False
NODE_LOCK = threading.Lock()


def is_sleeping():
    with NODE_LOCK:
        return NODE_SLEEP


def set_sleep(value: bool):
    global NODE_SLEEP
    with NODE_LOCK:
        NODE_SLEEP = value


# =====================================================
# DEBUG LOG
# =====================================================
@app.get("/debug/log")
def log_dump():
    return FileResponse("cluster/data/event_log.local.jsonl")


# =====================================================
# EXECUTE (BLOCKED IN SLEEP)
# =====================================================
@app.post("/execute")
def execute_endpoint(event: ClusterEvent):

    if is_sleeping():
        return {"error": "node sleeping"}

    return execute_event(event)


# =====================================================
# ACK
# =====================================================
@app.post("/ack")
def ack(event: ClusterEvent):

    log_state("green", "[ACK]", f"{event.event_id} received", 3)

    return {
        "ok": True,
        "event_id": event.event_id
    }


# =====================================================
# REPLAY
# =====================================================
@app.post("/replay")
def replay():

    def handler(event):
        return None

    replay_events(handler)

    return {"ok": True}


# =====================================================
# EVENT FLOW
# =====================================================
@app.post("/event")
def handle_event(event: ClusterEvent):

    if is_sleeping():
        log_state("red", "(SLEEP DROP EVENT)", event.event_id, 3)
        return {"error": "node sleeping"}

    log_state("red", "(STILL ALIVE!)", event.event_id, 3)

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


# =====================================================
# SLEEP / WAKEUP (LOCAL ONLY)
# =====================================================
@app.post("/sleep")
def sleep():

    set_sleep(True)

    log_state("red", "(SLEEP)", f"{ctx.node_id} -> SLEEP", 3)

    return {"ok": True}


@app.post("/revive")
def revive():

    set_sleep(False)

    log_state("red", "(WAKEUP)", f"{ctx.node_id} -> WAKEUP", 3)

    return {"ok": True}


# =====================================================
# CLUSTER METADATA
# =====================================================
class Heartbeat(BaseModel):
    node_id: str
    state: str
    priority: int


@app.get("/health")
def health():
    return {
        "status": "ok",
        "node": ctx.node_id,
        "sleeping": is_sleeping()
    }


@app.get("/cluster")
def get_cluster():
    return cluster_state


@app.get("/leader")
def get_leader():
    return {"leader": compute_leader()}




@app.post("/heartbeat")
def heartbeat(hb: Heartbeat):

    with HB_LOCK:

        #if ctx.node_id == "lnx200nas":
         #   log_state("red", "(HB FREEZE 3s)", "sleeping 20s", 3)
            # time.sleep(3)

        if is_sleeping():
            log_state("white", "(NO HEARTBEAT)", f"{ctx.node_id} -> NO HEARTBEAT", 3)
            return {"ok": True, "ignored": True}

        #log_state("white", "(HEARTBEAT)", f"{ctx.node_id} -> HEARTBEAT", 3)

        cluster_state[hb.node_id] = {
            "state": hb.state,
            "priority": hb.priority,
            "last_seen": time.time(),
        }

        return {"ok": True}


# =====================================================
# BOOTSTRAP
# =====================================================
def run_node(config):

    ctx.node_id = config["node_id"]
    ctx.priority = config["priority"]

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
