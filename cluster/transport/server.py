from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
import time


app = FastAPI()


cluster_state = {}  # 👈 memoria local del nodo


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

@app.get("/cluster")
def get_cluster():

    return cluster_state

@app.post("/heartbeat")
def heartbeat(hb: Heartbeat):

    cluster_state[hb.node_id] = {
        "state": hb.state,
        "leader": hb.leader,
        "priority": hb.priority,
        "last_seen": time.time(),
    }

    print(
        f"HB RECEIVED: {hb.node_id} state={hb.state} leader={hb.leader}"
    )

    return {"ok": True}



def start_server(host="0.0.0.0", port=7000):

    uvicorn.run(
        app,
        host=host,
        port=port,
    )


if __name__ == "__main__":

    start_server()
