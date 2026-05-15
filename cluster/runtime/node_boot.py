
import threading
import time
import json
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from cluster.runtime.cluster_store import cluster_state
from cluster.node.node_runtime import NodeRuntime
from cluster.runtime.node_worker import NodeWorker
from cluster.runtime.leader import compute_leader
from cluster.runtime.bootstrap import load_or_bootstrap_config

import requests


from cluster.runtime.event import ClusterEvent, normalize_event
from cluster.runtime.event_router import (
    forward_to_leader,
    route_event
)

node_id = None

# -----------------------------
# API
# -----------------------------
app = FastAPI()


@app.post("/event")
def handle_event(event: ClusterEvent):

    event = normalize_event(event)

    leader = compute_leader()

    # soy leader → proceso directo
    if leader == node_id:
        return route_event(event)

    # no soy leader → forward
    return forward_to_leader(event)


@app.post("/route")
def route(event: ClusterEvent):

    event = normalize_event(event)

    return route_event(event)


@app.post("/execute")
def execute(event: ClusterEvent):

    print(f"[EXEC] {event.event_id} {event.type} @ {node_id}")

    return {
        "ok": True,
        "node": node_id,
        "event_id": event.event_id
    }




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


# -----------------------------
# BOOTSTRAP NODE
# -----------------------------
def run_node(config):


    global node_id
    node_id = config["node_id"]


    node = NodeRuntime(
        node_id=config["node_id"],
        priority=config["priority"],
    )

    worker = NodeWorker(
        node=node,
        peers=config["peers"],
        interval=1.0
    )

    # start worker thread
    t = threading.Thread(target=worker.start, daemon=True)
    t.start()

    # start API
    uvicorn.run(
        app,
        host=config.get("bind_host", "0.0.0.0"),
        port=config.get("bind_port", 7000)
    )


# -----------------------------
# ENTRYPOINT
# -----------------------------
if __name__ == "__main__":

    config = load_or_bootstrap_config()

    run_node(config)
