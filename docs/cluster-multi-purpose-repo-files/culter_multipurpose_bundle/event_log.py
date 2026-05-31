import json
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
        f.write(json.dumps(record) + "
")
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
