from pathlib import Path
out = Path('output')
out.mkdir(exist_ok=True)

cluster_event = '''from pydantic import BaseModel, Field
from typing import Optional
from uuid import uuid4
import time

from cluster.runtime.events.event_state import EventStatus


class ClusterEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    schema_version: str = "0.1"
    event_type: str
    payload: dict = Field(default_factory=dict)
    status: EventStatus = EventStatus.CREATED
    route_hops: list[str] = Field(default_factory=list)
    target_node: Optional[str] = None
    source_node: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    received_at: Optional[float] = None
    attempt: int = 0
    execution_key: Optional[str] = None

    def add_hop(self, hop: str):
        self.route_hops.append(hop)
        self.updated_at = time.time()

    def mark_status(self, status: EventStatus):
        self.status = status
        self.updated_at = time.time()

    def mark_received(self):
        self.received_at = time.time()
        self.updated_at = self.received_at
'''

node_runtime = '''from dataclasses import dataclass, field
import os
import time
import requests

from cluster.runtime.state import NodeState
from cluster.runtime.leader import compute_leader
from cluster.runtime.event_log import get_last_append_meta, load_events
from cluster.runtime.integrity import file_sha256, cluster_integrity_report
from cluster.utils.log_print import log_state


@dataclass(slots=True)
class NodeRuntimeState:
    node_id: str
    state: NodeState
    priority: int
    last_seen: float = field(default_factory=time.time)
    log_meta: dict = field(default_factory=dict)
    cluster_integrity: dict = field(default_factory=dict)
    active_streams: dict = field(default_factory=dict)

    def touch(self):
        self.last_seen = time.time()


class NodeRuntime:
    def __init__(self, node_id, priority):
        self.runtime_state = NodeRuntimeState(node_id=node_id, state=NodeState.BOOT, priority=priority)
        self.last_heartbeat = time.time()

    @property
    def node_id(self):
        return self.runtime_state.node_id

    @property
    def priority(self):
        return self.runtime_state.priority

    @property
    def state(self):
        return self.runtime_state.state

    @state.setter
    def state(self, new_state):
        self.runtime_state.state = new_state
        self.runtime_state.touch()

    def transition(self, new_state):
        if self.runtime_state.state == new_state:
            return
        print(f"[{self.node_id}] {self.runtime_state.state} -> {new_state}")
        self.state = new_state

    def tick(self):
        if self.state == NodeState.BOOT:
            self.transition(NodeState.STANDBY)
            return

        leader = compute_leader()
        if leader == self.node_id:
            if self.state == NodeState.STANDBY:
                log_state("yellow", "[CLUSTER]", f"[{self.node_id}] becoming ACTIVE", 3)
                self.transition(NodeState.ACTIVE)
        else:
            if self.state == NodeState.ACTIVE:
                log_state("yellow", "[CLUSTER]", f"[{self.node_id}] becoming STANDBY", 3)
                self.transition(NodeState.STANDBY)

    def _log_size(self):
        try:
            return len(load_events())
        except Exception:
            return 0

    def _file_size(self):
        try:
            return os.path.getsize("cluster/data/event_log.local.jsonl")
        except OSError:
            return 0

    def emit_heartbeat(self, peers):
        cluster_int = cluster_integrity_report()
        log_meta = {
            **get_last_append_meta(),
            "log_size": self._log_size(),
            "file_size": self._file_size(),
            "file_hash": file_sha256("cluster/data/event_log.local.jsonl"),
        }
        self.runtime_state.log_meta = log_meta
        self.runtime_state.cluster_integrity = cluster_int
        hb = {
            "node_id": self.node_id,
            "state": self.state.value,
            "priority": self.priority,
            "log_meta": log_meta,
            "cluster_integrity": {
                "integrity_ok": cluster_int.get("integrity_ok", False),
                "alive_nodes": cluster_int.get("alive_nodes", []),
                "per_peer": cluster_int.get("per_peer", {}),
            },
            "streams": self.runtime_state.active_streams,
        }
        for peer in peers:
            url = f"http://{peer['host']}:{peer['port']}/heartbeat"
            try:
                requests.post(url, json=hb, timeout=2)
            except requests.exceptions.RequestException:
                pass
'''

event_log = '''import json
import os
from typing import Dict, List, Optional

from cluster.runtime.events.cluster_event import ClusterEvent
from cluster.runtime.events.event_state import EventStatus

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "cluster", "data")
LOCAL_LOG_PATH = os.path.join(DATA_DIR, "event_log.local.jsonl")
STATE_PATH = os.path.join(DATA_DIR, "last_append.state.json")


def ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def get_local_log_path() -> str:
    return LOCAL_LOG_PATH


def get_state_path() -> str:
    return STATE_PATH


def get_replica_log_path(node_id: str) -> str:
    return os.path.join(DATA_DIR, f"event_log.{node_id}.jsonl")


def list_replica_log_paths() -> List[str]:
    if not os.path.exists(DATA_DIR):
        return []
    out: List[str] = []
    for name in sorted(os.listdir(DATA_DIR)):
        if not name.startswith("event_log."):
            continue
        if not name.endswith(".jsonl"):
            continue
        if name == "event_log.local.jsonl":
            continue
        out.append(os.path.join(DATA_DIR, name))
    return out


def load_events_from_path(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def write_text_atomic(path: str, content: str):
    ensure_dir()
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


def read_local_log_text() -> str:
    if not os.path.exists(LOCAL_LOG_PATH):
        return ""
    with open(LOCAL_LOG_PATH, "r", encoding="utf-8") as f:
        return f.read()


def write_replica_log(node_id: str, content: str):
    write_text_atomic(get_replica_log_path(node_id), content)


def read_state() -> dict:
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_state(state: dict):
    ensure_dir()
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def clear_state():
    try:
        os.remove(STATE_PATH)
    except FileNotFoundError:
        pass


def load_events() -> List[dict]:
    return load_events_from_path(LOCAL_LOG_PATH)


def load_local_events() -> List[dict]:
    return load_events_from_path(LOCAL_LOG_PATH)


def load_replica_events(node_id: str) -> List[dict]:
    return load_events_from_path(get_replica_log_path(node_id))


def load_all_replica_events() -> List[dict]:
    events: List[dict] = []
    for path in list_replica_log_paths():
        events.extend(load_events_from_path(path))
    return events


def load_cluster_events() -> List[dict]:
    return load_all_replica_events()


def get_last_append_meta() -> dict:
    state = read_state()
    return {
        "dirty": bool(state.get("dirty", False)),
        "last_append_event_id": state.get("last_append_event_id"),
        "last_append_created_at": state.get("last_append_created_at"),
    }


def _normalize_event(e: dict) -> dict:
    e = dict(e)
    e["schema_version"] = str(e.get("schema_version", "0.1"))
    e.setdefault("received_at", None)
    e.setdefault("attempt", 0)
    e.setdefault("route_hops", [])
    e.setdefault("execution_key", None)
    return e


def _latest_map(events: List[dict]) -> Dict[str, dict]:
    latest: Dict[str, dict] = {}
    for e in events:
        e = _normalize_event(e)
        latest[e["event_id"]] = e
    return latest


def rebuild_event_state_index() -> Dict[str, dict]:
    return _latest_map(load_events())


def get_latest_event(event_id: str) -> Optional[dict]:
    events = load_events()
    for e in reversed(events):
        if e["event_id"] == event_id:
            return _normalize_event(e)
    return None


def get_created_events():
    latest = rebuild_event_state_index()
    domain_events = [ClusterEvent(**e) for e in latest.values()]
    return [e for e in domain_events if e.status == EventStatus.CREATED]


def get_completed_event_ids():
    latest = rebuild_event_state_index()
    domain_events = [ClusterEvent(**e) for e in latest.values()]
    return {e.event_id for e in domain_events if e.status == EventStatus.COMPLETED}


def append_event(event: ClusterEvent):
    ensure_dir()
    record = {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "schema_version": str(event.schema_version),
        "created_at": event.created_at,
        "received_at": getattr(event, "received_at", None),
        "trace_id": event.trace_id,
        "target_node": event.target_node,
        "route_hops": event.route_hops,
        "status": event.status.value if hasattr(event.status, "value") else event.status,
        "attempt": event.attempt,
        "payload": event.payload,
    }
    if record["status"] == EventStatus.COMPLETED.value:
        existing = load_events()
        if any(e.get("event_id") == event.event_id and e.get("status") == EventStatus.COMPLETED.value for e in existing):
            return
    with open(LOCAL_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
        f.flush()
        os.fsync(f.fileno())
    write_state({
        "dirty": True,
        "last_append_event_id": event.event_id,
        "last_append_created_at": event.created_at,
    })


def replay_events(handler):
    events = load_events()
    for raw in events:
        event = ClusterEvent(**_normalize_event(raw))
        handler(event)
'''

api_app = '''import os
import time
import logging
import requests

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from cluster.runtime.cluster_store import cluster_state
from cluster.runtime.leader import compute_leader
from cluster.runtime.registry import CLUSTER_REGISTRY
from cluster.runtime.event_log import (
    replay_events,
    get_local_log_path,
    get_replica_log_path,
    write_replica_log,
)
from cluster.runtime.ingest import ingest_event
from cluster.runtime.events.cluster_event import ClusterEvent
from cluster.runtime import context as ctx
from cluster.utils.log_print import log_state
from cluster.runtime.worker.event_worker import execute_event
from cluster.runtime.node_runtime import NodeState
from cluster.runtime.integrity import local_integrity_api, cluster_integrity_report, canonicalize


logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("requests").setLevel(logging.ERROR)

app = FastAPI()


class Heartbeat(BaseModel):
    node_id: str
    state: str
    priority: int
    log_meta: dict | None = None
    cluster_integrity: dict | None = None
    streams: dict | None = None


@app.get("/debug/log")
def log_dump():
    path = get_local_log_path()
    if not os.path.exists(path):
        return PlainTextResponse("", status_code=200)
    return FileResponse(path, media_type="text/plain")


@app.get("/debug/log/local")
def log_dump_local():
    path = get_local_log_path()
    if not os.path.exists(path):
        return PlainTextResponse("", status_code=200)
    return FileResponse(path, media_type="text/plain")


@app.get("/debug/log/replica/{node_id}")
def log_dump_replica(node_id: str):
    path = get_replica_log_path(node_id)
    if not os.path.exists(path):
        return PlainTextResponse("", status_code=404)
    return FileResponse(path, media_type="text/plain")


@app.post("/debug/log/replica/{node_id}")
async def log_replica_write(node_id: str, request: Request):
    content = await request.body()
    text = content.decode("utf-8") if content else ""
    write_replica_log(node_id, text)
    return {"ok": True, "node_id": node_id, "path": get_replica_log_path(node_id), "bytes": len(content)}


@app.post("/execute")
def execute_endpoint(event: ClusterEvent):
    if ctx.node.state == NodeState.ISOLATED:
        return {"error": "node isolated"}
    return execute_event(event)


@app.post("/ack")
def ack(event: ClusterEvent):
    log_state("green", "[ACK]", f"{event.event_id} received", 3)
    return {"ok": True, "event_id": event.event_id}


@app.post("/replay")
def replay():
    def handler(event):
        return None
    replay_events(handler)
    return {"ok": True}


@app.post("/event")
def handle_event(event: ClusterEvent):
    if ctx.node.state == NodeState.ISOLATED:
        return {"error": "node isolated"}

    leader = compute_leader()
    if not leader:
        log_state("red", "(NO LEADER)", event.event_id, 3)
        return {"error": "no leader"}

    if leader != ctx.node_id:
        msg = event.payload.get("msg", "<no-msg>")
        log_state("cyan", "[EVENT FWD]", f"{msg:12} -> {leader}", 3)
        node = CLUSTER_REGISTRY[leader]
        url = f"http://{node['host']}:{node['port']}/event"
        try:
            resp = requests.post(url, json=event.model_dump(), timeout=2)
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    result = ingest_event(event, ctx.node_id)
    return {"status": "ok", "event_id": event.event_id, "result": result}


@app.post("/sleep")
def sleep():
    log_state("red", "- SLEEP -", f"{ctx.node_id} -> SLEEP", 3)
    ctx.node.transition(NodeState.ISOLATED)
    return {"ok": True, "node": ctx.node_id, "state": ctx.node.state.value}


@app.post("/revive")
def revive():
    log_state("red", "- WAKEUP -", f"{ctx.node_id} -> WAKEUP", 3)
    ctx.node.transition(NodeState.STANDBY)
    return {"ok": True, "node": ctx.node_id, "state": ctx.node.state.value}


@app.get("/health")
def health():
    return {"status": "ok", "node": ctx.node_id, "sleeping": ctx.node.state == NodeState.ISOLATED}


@app.get("/cluster")
def get_cluster():
    return cluster_state


@app.get("/leader")
def get_leader():
    return {"leader": compute_leader()}


@app.post("/heartbeat")
def heartbeat(hb: Heartbeat):
    if ctx.node.state == NodeState.ISOLATED:
        return {"error": "node isolated"}

    existing = cluster_state.get(hb.node_id, {})
    cluster_state[hb.node_id] = {
        "state": hb.state,
        "priority": hb.priority,
        "last_seen": time.time(),
        "log_meta": hb.log_meta or {},
        "cluster_integrity": hb.cluster_integrity or existing.get("cluster_integrity", {}),
        "streams": hb.streams or existing.get("streams", {}),
    }

    return {"ok": True}


@app.get("/integrity")
def integrity():
    return local_integrity_api()


@app.get("/integrity/cluster")
def integrity_cluster():
    return cluster_integrity_report()
'''

files = {
    'cluster_runtime_cluster_event_patch.py': cluster_event,
    'cluster_runtime_node_runtime_patch.py': node_runtime,
    'cluster_runtime_event_log_patch.py': event_log,
    'cluster_runtime_api_app_patch.py': api_app,
}
for name, content in files.items():
    (out / name).write_text(content, encoding='utf-8')

print('patches ready')
