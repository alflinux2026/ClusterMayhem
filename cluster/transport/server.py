
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
import time

from cluster.runtime.cluster_store import get_active_cluster, cleanup_cluster

app = FastAPI()


def compute_leader():
    now = time.time()

    active = {
        n: data["priority"]
        for n, data in get_active_cluster().items()
        if data["state"] in ("BOOT", "ACTIVE")
    }

    if not active:
        return None

    return min(active, key=active.get)


print("SERVER PROCESS STARTED")


class Heartbeat(BaseModel):
    node_id: str
    state: str
    leader: str | None = None
    priority: int | None = None
    timestamp: float | None = None


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/cluster")
def get_cluster():
    cleanup_cluster()
    return get_active_cluster()


@app.get("/leader")
def leader():
    return {"leader": compute_leader()}


@app.post("/heartbeat")
def heartbeat(hb: Heartbeat):

    get_active_cluster()[hb.node_id] = {
        "state": hb.state,
        "priority": hb.priority,
        "last_seen": time.time(),
    }

    return {"ok": True}


def start_server(host="0.0.0.0", port=7000):
    uvicorn.run(app, host=host, port=port)


def register_local_node(node_id, state, priority):

    get_active_cluster()[node_id] = {
        "state": state,
        "leader": None,
        "priority": priority,
        "last_seen": time.time(),
    }


if __name__ == "__main__":
    start_server()
