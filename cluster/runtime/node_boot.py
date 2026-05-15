
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


# -----------------------------
# CONFIG LOAD
# -----------------------------

def load_config(path="config/node.local.json"):
    with open(path, "r") as f:
        return json.load(f)


# -----------------------------
# API
# -----------------------------
app = FastAPI()


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

    config = load_config()

    run_node(config)
