from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn


app = FastAPI()


class HeartbeatMessage(BaseModel):

    node_id: str
    state: str
    leader: str | None = None


@app.get("/health")
async def health():

    return {
        "status": "ok"
    }


@app.post("/heartbeat")
async def heartbeat(msg: HeartbeatMessage):

    print(
        f"HEARTBEAT from={msg.node_id} "
        f"state={msg.state} "
        f"leader={msg.leader}"
    )

    return {
        "received": True
    }


def start_server(host="0.0.0.0", port=7000):

    uvicorn.run(
        app,
        host=host,
        port=port,
    )


if __name__ == "__main__":

    start_server()
