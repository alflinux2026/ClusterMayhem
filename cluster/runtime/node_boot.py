import threading
import time
import uvicorn
import logging
import requests

from fastapi import FastAPI
from pydantic import BaseModel

from cluster.runtime.cluster_store import cluster_state
from cluster.runtime.node_worker import NodeWorker
from cluster.node.node_runtime import NodeRuntime
from cluster.runtime.leader import compute_leader
from cluster.runtime.bootstrap import load_or_bootstrap_config
from cluster.runtime.registry import CLUSTER_REGISTRY

from cluster.runtime.event_log import append_event, replay_events
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


# -------------------------
# ACK (FINAL STATE ONLY)
# -------------------------
@app.post("/ack")
def ack(event: ClusterEvent):

    log_state("green", "[ACK]", f"{event.event_id} completed", 3)

    event.mark_status("completed")
    append_event(event)

    return {"ok": True}


# -------------------------
# REPLAY
# -------------------------
@app.post("/replay")
def replay():

    def handler(event):
        return None

    replay_events(handler)

    return {"ok": True}


# =========================
# SINGLE ENTRYPOINT
# =========================
@app.post("/event")
def handle_event(event: ClusterEvent):


    leader = compute_leader()
    log_state("cyan", "(LEADER)", f"computed={leader}", 3)

    if not leader:
        log_state("red", "(NO LEADER)", event.event_id, 3)
        return {"error": "no leader"}

    # -----------------------------------
    # NOT LEADER → forward to leader
    # -----------------------------------
    if leader != ctx.node_id:

        log_state("cyan", "[EVENT IN]", f"{event.event_id} type={event.event_type}", 3)

        log_state("cyan", "[FORWARD]", f"{event.event_id} -> {leader}", 3)

        node = CLUSTER_REGISTRY[leader]
        url = f"http://{node['host']}:{node['port']}/event"

        resp = requests.post(
            url,
            json=event.model_dump(),
            timeout=2
        )

        return resp.json()

    # -----------------------------------
    # LEADER → INGEST ONLY
    # -----------------------------------
    return ingest_event(event, ctx.node_id)


# =========================
# CLUSTER METADATA
# =========================
class Heartbeat(BaseModel):
    node_id: str
    state: str
    priority: int


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


def is_alive(data, timeout=3.0):
    return (time.time() - data["last_seen"]) < timeout


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
