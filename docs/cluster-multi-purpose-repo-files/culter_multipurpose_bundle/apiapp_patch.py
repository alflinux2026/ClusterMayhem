from __future__ import annotations

import os
import time
import logging
import requests

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, PlainTextResponse

from cluster.runtime.clusterstore import clusterstate
from cluster.runtime.leader import computeleader
from cluster.runtime.registry import CLUSTERREGISTRY
from cluster.runtime.eventlog import replayevents, getlocallogpath, getreplicalogpath, writereplicalog
from cluster.runtime.ingest import ingestevent
from cluster.runtime.events.clusterevent import ClusterEvent
from cluster.runtime import context as ctx
from cluster.runtime.worker.eventworker import executeevent
from cluster.runtime.state import NodeState
from cluster.runtime.models import HeartbeatState

logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("requests").setLevel(logging.ERROR)

app = FastAPI()


@app.get("/debug/log")
def logdump():
    path = getlocallogpath()
    if not os.path.exists(path):
        return PlainTextResponse("", status_code=200)
    return FileResponse(path, media_type="text/plain")


@app.get("/debug/log/local")
def logdumplocal():
    path = getlocallogpath()
    if not os.path.exists(path):
        return PlainTextResponse("", status_code=200)
    return FileResponse(path, media_type="text/plain")


@app.get("/debug/log/replica/{nodeid}")
def logdumpreplica(nodeid: str):
    path = getreplicalogpath(nodeid)
    if not os.path.exists(path):
        return PlainTextResponse("", status_code=404)
    return FileResponse(path, media_type="text/plain")


@app.post("/debug/log/replica/{nodeid}")
async def logreplicawrite(nodeid: str, request: Request):
    content = await request.body()
    text = content.decode("utf-8") if content else ""
    writereplicalog(nodeid, text)
    return {"ok": True, "node_id": nodeid, "path": getreplicalogpath(nodeid), "bytes": len(content)}


@app.post("/execute")
def executeendpoint(event: ClusterEvent):
    if ctx.node.state == NodeState.ISOLATED:
        return {"error": "node isolated"}
    return executeevent(event)


@app.post("/ack")
def ackevent(event: ClusterEvent):
    return {"ok": True, "event_id": event.event_id}


@app.post("/replay")
def replay():
    def handle(event):
        return None
    replayevents(handle)
    return {"ok": True}


@app.post("/event")
def handleevent(event: ClusterEvent):
    if ctx.node.state == NodeState.ISOLATED:
        return {"error": "node isolated"}

    leader = computeleader()
    if not leader:
        return {"error": "no leader"}

    if leader != ctx.nodeid:
        node = CLUSTERREGISTRY[leader]
        url = f"http://{node.host}:{node.port}/event"
        try:
            resp = requests.post(url, json=event.model_dump(), timeout=2)
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    result = ingestevent(event, ctx.nodeid)
    return {"status": "ok", "event_id": event.event_id, "result": result}


@app.post("/heartbeat")
def heartbeat(hb: HeartbeatState):
    if ctx.node.state == NodeState.ISOLATED:
        return {"error": "node isolated"}

    existing = clusterstate.get(hb.node_id, {})
    clusterstate[hb.node_id] = {
        **existing,
        "state": hb.state,
        "priority": hb.priority,
        "lastseen": time.time(),
        "logmeta": hb.log_meta or {},
        "clusterintegrity": hb.cluster_integrity or existing.get("clusterintegrity", {}),
        "streams": hb.streams or {},
    }
    return {"ok": True}
