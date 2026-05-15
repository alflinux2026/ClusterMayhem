import threading
import time
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from cluster.runtime.cluster_store import cluster_state
from cluster.node.node_runtime import NodeRuntime
from cluster.workers.cluster_worker import ClusterWorker
from cluster.runtime.node_worker import NodeWorker

from cluster.runtime.leader import compute_leader


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
def run_node(node_id: str, priority: int, peers: list[str]):



    node = NodeRuntime(
        node_id=node_id,
        priority=priority,

    )

    worker = NodeWorker(node=node, peers=peers, interval=1.0)
    worker.start()


    # -------------------------
    # worker thread
    # -------------------------
    t = threading.Thread(target=worker.start, daemon=True)
    t.start()

    # -------------------------
    # API thread
    # -------------------------
    uvicorn.run(app, host="0.0.0.0", port=7000)


# -----------------------------
# ENTRYPOINT
# -----------------------------
if __name__ == "__main__":

    import sys

    node_id = sys.argv[1]
    priority = int(sys.argv[2])

    peers = [
        {"host": "100.100.1.200", "port": 7000},
        {"host": "100.100.1.202", "port": 7000},
        {"host": "100.100.1.203", "port": 7000},
    ]

    run_node(node_id, priority, peers)
