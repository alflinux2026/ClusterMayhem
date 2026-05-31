from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from cluster.runtime.events.cluster_event import ClusterEvent
from cluster.runtime.events.event_state import EventStatus
from cluster.runtime.models import EventEnvelope, SegmentMeta, StreamKey
from cluster.runtime.serialization import event_to_record, record_to_event, segment_meta_to_record, record_to_segment_meta

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "cluster" / "data"
STATE_SUFFIX = ".state.json"


def ensure_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def stream_dir(stream: StreamKey) -> Path:
    return DATA_DIR / stream.tenant_id / stream.app_id / stream.data_type / stream.schema_version


def current_log_path(stream: StreamKey) -> Path:
    return stream_dir(stream) / "current.jsonl"


def segments_dir(stream: StreamKey) -> Path:
    return stream_dir(stream) / "segments"


def segment_log_path(stream: StreamKey, segment_id: str) -> Path:
    return segments_dir(stream) / f"{segment_id}.jsonl"


def segment_meta_path(stream: StreamKey, segment_id: str) -> Path:
    return segments_dir(stream) / f"{segment_id}.meta.json"


def state_path(stream: StreamKey) -> Path:
    return stream_dir(stream) / f"current{STATE_SUFFIX}"


def get_local_log_path(stream: StreamKey | None = None) -> str:
    if stream is None:
        return str(DATA_DIR / "event_log.local.jsonl")
    return str(current_log_path(stream))


def get_replica_log_path(node_id: str) -> str:
    return str(DATA_DIR / f"event_log.{node_id}.jsonl")


def list_replica_log_paths() -> List[str]:
    if not DATA_DIR.exists():
        return []
    out: List[str] = []
    for path in sorted(DATA_DIR.iterdir()):
        if path.is_file() and path.name.startswith("event_log.") and path.name.endswith(".jsonl") and path.name != "event_log.local.jsonl":
            out.append(str(path))
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


def write_text_atomic(path: str, content: str) -> None:
    ensure_dir()
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = p.with_suffix(p.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, p)


def read_local_log_text(stream: StreamKey | None = None) -> str:
    path = get_local_log_path(stream)
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_replica_log(node_id: str, content: str) -> None:
    write_text_atomic(get_replica_log_path(node_id), content)


def read_state(stream: StreamKey) -> dict:
    p = state_path(stream)
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_state(stream: StreamKey, state: dict) -> None:
    ensure_dir()
    p = state_path(stream)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def clear_state(stream: StreamKey) -> None:
    try:
        os.remove(state_path(stream))
    except FileNotFoundError:
        pass


def append_event(event: ClusterEvent | EventEnvelope) -> None:
    ensure_dir()
    if isinstance(event, EventEnvelope):
        record = event_to_record(event)
        stream = event.stream
    else:
        record = event_to_record(EventEnvelope.from_cluster_event(event))
        stream = event_to_record(EventEnvelope.from_cluster_event(event))["stream"]
    path = current_log_path(StreamKey(**stream)) if isinstance(stream, dict) else current_log_path(stream)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "
")
        f.flush()
        os.fsync(f.fileno())
    write_state(StreamKey(**record["stream"]), {
        "dirty": True,
        "last_append_event_id": record["event_id"],
        "last_append_created_at": record.get("created_at"),
        "stream_id": record["stream"]["stream_id"],
    })


def load_events(stream: StreamKey | None = None) -> List[dict]:
    if stream is None:
        return load_events_from_path(str(DATA_DIR / "event_log.local.jsonl"))
    return load_events_from_path(str(current_log_path(stream)))


def load_local_events(stream: StreamKey | None = None) -> List[dict]:
    return load_events(stream)


def load_replica_events(node_id: str) -> List[dict]:
    return load_events_from_path(get_replica_log_path(node_id))


def load_all_replica_events() -> List[dict]:
    events: List[dict] = []
    for path in list_replica_log_paths():
        events.extend(load_events_from_path(path))
    return events


def load_cluster_events() -> List[dict]:
    return load_all_replica_events()


def get_last_append_meta(stream: StreamKey | None = None) -> dict:
    if stream is None:
        return {}
    state = read_state(stream)
    return {
        "dirty": bool(state.get("dirty", False)),
        "last_append_event_id": state.get("last_append_event_id"),
        "last_append_created_at": state.get("last_append_created_at"),
        "stream_id": state.get("stream_id", stream.stream_id()),
    }


def _normalize_event(e: dict) -> dict:
    e = dict(e)
    e["schema_version"] = str(e.get("schema_version", "0.1"))
    e.setdefault("received_at", None)
    e.setdefault("attempt", 0)
    e.setdefault("route_hops", [])
    e.setdefault("execution_key", None)
    return e


def rebuild_event_state_index(stream: StreamKey | None = None) -> Dict[str, dict]:
    latest: Dict[str, dict] = {}
    for e in load_events(stream):
        e = _normalize_event(e)
        latest[e["event_id"]] = e
    return latest


def get_latest_event(event_id: str, stream: StreamKey | None = None) -> Optional[dict]:
    events = load_events(stream)
    for e in reversed(events):
        if e["event_id"] == event_id:
            return _normalize_event(e)
    return None


def get_created_events(stream: StreamKey | None = None):
    latest = rebuild_event_state_index(stream)
    domain_events = [record_to_event(e) for e in latest.values()]
    return [e for e in domain_events if e.status == EventStatus.CREATED]


def get_completed_event_ids(stream: StreamKey | None = None):
    latest = rebuild_event_state_index(stream)
    domain_events = [record_to_event(e) for e in latest.values()]
    return {e.event_id for e in domain_events if e.status == EventStatus.COMPLETED}


def replay_events(handler, stream: StreamKey | None = None):
    events = load_events(stream)
    for raw in events:
        event = record_to_event(_normalize_event(raw))
        handler(event)


def seal_segment(meta: SegmentMeta) -> None:
    ensure_dir()
    p = segment_meta_path(meta.stream, meta.segment_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(segment_meta_to_record(meta), f, ensure_ascii=False, indent=2)


def load_segment_meta(stream: StreamKey, segment_id: str) -> SegmentMeta | None:
    p = segment_meta_path(stream, segment_id)
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return record_to_segment_meta(raw)
    except (OSError, json.JSONDecodeError):
        return None
