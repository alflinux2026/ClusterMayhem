from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from cluster.runtime.models import EventEnvelope, EventStatus, SegmentMeta, StreamKey
from cluster.runtime.serialization import event_to_record, record_to_event, segment_meta_to_record

BASEDIR = Path(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
DATADIR = BASEDIR / "cluster" / "data"
STATE_SUFFIX = ".state.json"


def ensuredir() -> None:
    DATADIR.mkdir(parents=True, exist_ok=True)


def stream_dir(stream: StreamKey) -> Path:
    return DATADIR / stream.tenant_id / stream.app_id / stream.data_type / stream.schema_version


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


def getlocallogpath(stream: StreamKey | None = None) -> str:
    if stream is None:
        return str(DATADIR / "eventlog.local.jsonl")
    return str(current_log_path(stream))


def getreplicalogpath(nodeid: str) -> str:
    return str(DATADIR / f"eventlog.{nodeid}.jsonl")


def listreplicalogpaths() -> List[str]:
    if not DATADIR.exists():
        return []
    out: List[str] = []
    for path in sorted(DATADIR.iterdir()):
        if path.is_file() and path.name.startswith("eventlog.") and path.name.endswith(".jsonl") and path.name != "eventlog.local.jsonl":
            out.append(str(path))
    return out


def loadeventsfrompath(path: str) -> List[dict]:
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


def writetextatomic(path: str, content: str) -> None:
    ensuredir()
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def readlocallogtext(stream: StreamKey | None = None) -> str:
    path = getlocallogpath(stream)
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def writereplicalog(nodeid: str, content: str) -> None:
    writetextatomic(getreplicalogpath(nodeid), content)


def readstate(stream: StreamKey) -> dict:
    path = state_path(stream)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def writestate(stream: StreamKey, state: dict) -> None:
    ensuredir()
    path = state_path(stream)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def clearstate(stream: StreamKey) -> None:
    try:
        os.remove(state_path(stream))
    except FileNotFoundError:
        pass


def append_event(event: EventEnvelope) -> None:
    ensuredir()
    path = current_log_path(event.stream)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = event_to_record(event)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "
")
        f.flush()
        os.fsync(f.fileno())
    writestate(event.stream, {
        "dirty": True,
        "last_append_event_id": event.event_id,
        "last_append_created_at": event.created_at,
        "stream_id": event.stream.stream_id(),
    })


def getlastappendmeta(stream: StreamKey | None = None) -> dict:
    if stream is None:
        return {}
    state = readstate(stream)
    return {
        "dirty": bool(state.get("dirty", False)),
        "last_append_event_id": state.get("last_append_event_id"),
        "last_append_created_at": state.get("last_append_created_at"),
        "stream_id": state.get("stream_id", stream.stream_id()),
    }


def load_events(stream: StreamKey) -> List[EventEnvelope]:
    path = current_log_path(stream)
    return [record_to_event(r) for r in loadeventsfrompath(str(path))]


def getcreatedevents(stream: StreamKey | None = None) -> List[EventEnvelope]:
    if stream is None:
        return []
    return [e for e in load_events(stream) if e.status == EventStatus.CREATED]


def getcompletedeventids(stream: StreamKey | None = None) -> List[str]:
    if stream is None:
        return []
    return [e.event_id for e in load_events(stream) if e.status == EventStatus.COMPLETED]


def seal_segment(meta: SegmentMeta) -> None:
    ensuredir()
    meta.node_id = meta.node_id or "unknown"
    meta.file_name = meta.file_name or f"{meta.segment_id}.jsonl"
    meta_dir = segments_dir(meta.stream)
    meta_dir.mkdir(parents=True, exist_ok=True)
    with open(segment_meta_path(meta.stream, meta.segment_id), "w", encoding="utf-8") as f:
        json.dump(segment_meta_to_record(meta), f, ensure_ascii=False, indent=2)


def replayevents(handler) -> None:
    for path in listreplicalogpaths():
        for raw in loadeventsfrompath(path):
            try:
                event = record_to_event(raw)
                handler(event)
            except Exception:
                continue
