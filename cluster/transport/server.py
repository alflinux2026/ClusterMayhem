from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
import time

NODE_TIMEOUT = 3.0  # segundos

from cluster.runtime.cluster_store import cluster_state


app = FastAPI()


print("SERVER PROCESS STARTED")

print("SERVER cluster_state id", id(cluster_state))

class Heartbeat(BaseModel):
    node_id: str
    state: str
    leader: str | None = None
    priority: int | None = None
    timestamp: float | None = None


@app.get("/health")
async def health():

    return {
        "status": "ok"
    }

def is_alive(data):
    return (time.time() - data["last_seen"]) < NODE_TIMEOUT


def get_active_cluster():
    return {
        node_id: data
        for node_id, data in cluster_state.items()
        if is_alive(data)
    }

@app.get("/cluster")
def get_cluster():
    now = time.time()

    return {
        node_id: data
        for node_id, data in cluster_state.items()
        if (now - data["last_seen"]) < NODE_TIMEOUT
    }

import time


def is_alive(data):
    return (time.time() - data["last_seen"]) < NODE_TIMEOUT


def compute_leader():
    active = {
        n: data["priority"]
        for n, data in cluster_state.items()
        if is_alive(data) and data["state"] in ("BOOT", "ACTIVE")
    }

    if not active:
        return None

    return min(active, key=active.get)


@app.get("/leader")
def leader():
    return {"leader": compute_leader()}

@app.post("/heartbeat")
def heartbeat(hb: Heartbeat):

    cluster_state[hb.node_id] = {
        "state": hb.state,
        "leader": hb.leader,
        "priority": hb.priority,
        "last_seen": time.time(),
    }

    cleanup_cluster()   # 👈 AQUÍ

    return {"ok": True}



def start_server(host="0.0.0.0", port=7000):

    uvicorn.run(
        app,
        host=host,
        port=port,
    )

def get_leader(cluster_state):

    leaders = {}

    for node_id, data in cluster_state.items():

        if data["state"] == "ACTIVE":
            leaders[node_id] = data["priority"]

    if not leaders:
        return None

    return min(leaders, key=leaders.get)

def register_local_node(
    node_id,
    state,
    priority,
    ):

    print("REGISTER cluster_state id", id(cluster_state))

    cluster_state[node_id] = {
        "state": state,
        "leader": None,
        "priority": priority,
        "last_seen": time.time(),
    }

def cleanup_cluster():
    now = time.time()

    to_delete = [
        node_id
        for node_id, data in cluster_state.items()
        if now - data["last_seen"] > NODE_TIMEOUT
    ]

    for node_id in to_delete:
        print(f"[GC] removing {node_id}")
        del cluster_state[node_id]


if __name__ == "__main__":

    start_server()
