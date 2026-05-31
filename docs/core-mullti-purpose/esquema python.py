from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from uuid import uuid4
import time


class EventStatus(str, Enum):
    CREATED = "created"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


class NodeState(str, Enum):
    BOOT = "BOOT"
    DISCOVERING = "DISCOVERING"
    STANDBY = "STAND-BY"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    ISOLATED = "ISOLATED"
    OFFLINE = "OFFLINE"


@dataclass(frozen=True, slots=True)
class StreamKey:
    tenant_id: str
    app_id: str
    data_type: str
    schema_version: str = "v1"

    def stream_id(self) -> str:
        return f"{self.tenant_id}.{self.app_id}.{self.data_type}.{self.schema_version}"

    def path_parts(self) -> list[str]:
        return [self.tenant_id, self.app_id, self.data_type, self.schema_version]


@dataclass(slots=True)
class EventEnvelope:
    event_id: str = field(default_factory=lambda: str(uuid4()))
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    stream: StreamKey = field(default=None)
    event_type: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    status: EventStatus = EventStatus.CREATED
    route_hops: list[str] = field(default_factory=list)

    source_node: Optional[str] = None
    target_node: Optional[str] = None
    execution_key: Optional[str] = None

    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    received_at: Optional[float] = None
    attempt: int = 0

    def add_hop(self, hop: str) -> None:
        self.route_hops.append(hop)
        self.updated_at = time.time()

    def mark_status(self, status: EventStatus) -> None:
        self.status = status
        self.updated_at = time.time()

    def mark_received(self) -> None:
        self.received_at = time.time()
        self.updated_at = self.received_at

    def to_record(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "trace_id": self.trace_id,
            "stream_id": self.stream.stream_id() if self.stream else None,
            "tenant_id": self.stream.tenant_id if self.stream else None,
            "app_id": self.stream.app_id if self.stream else None,
            "data_type": self.stream.data_type if self.stream else None,
            "schema_version": self.stream.schema_version if self.stream else None,
            "event_type": self.event_type,
            "payload": self.payload,
            "status": self.status.value,
            "route_hops": self.route_hops,
            "source_node": self.source_node,
            "target_node": self.target_node,
            "execution_key": self.execution_key,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "received_at": self.received_at,
            "attempt": self.attempt,
        }


@dataclass(slots=True)
class SegmentMeta:
    stream: StreamKey
    segment_id: str

    created_at: float = field(default_factory=time.time)
    sealed_at: Optional[float] = None

    first_event_id: Optional[str] = None
    last_event_id: Optional[str] = None
    min_seq: Optional[int] = None
    max_seq: Optional[int] = None

    event_count: int = 0
    size_bytes: int = 0
    sha256: Optional[str] = None

    sealed: bool = False
    dirty: bool = True

    node_id: Optional[str] = None
    file_name: Optional[str] = None

    def seal(self, sha256: str, size_bytes: int) -> None:
        self.sealed = True
        self.dirty = False
        self.sealed_at = time.time()
        self.sha256 = sha256
        self.size_bytes = size_bytes

    def to_record(self) -> dict[str, Any]:
        return {
            "stream_id": self.stream.stream_id(),
            "tenant_id": self.stream.tenant_id,
            "app_id": self.stream.app_id,
            "data_type": self.stream.data_type,
            "schema_version": self.stream.schema_version,
            "segment_id": self.segment_id,
            "created_at": self.created_at,
            "sealed_at": self.sealed_at,
            "first_event_id": self.first_event_id,
            "last_event_id": self.last_event_id,
            "min_seq": self.min_seq,
            "max_seq": self.max_seq,
            "event_count": self.event_count,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "sealed": self.sealed,
            "dirty": self.dirty,
            "node_id": self.node_id,
            "file_name": self.file_name,
        }


@dataclass(slots=True)
class NodeState:
    node_id: str
    state: str
    priority: int
    last_seen: float = field(default_factory=time.time)

    log_meta: dict[str, Any] = field(default_factory=dict)
    cluster_integrity: dict[str, Any] = field(default_factory=dict)

    active_streams: dict[str, dict[str, Any]] = field(default_factory=dict)

    def touch(self) -> None:
        self.last_seen = time.time()


@dataclass(slots=True)
class HeartbeatState:
    node_id: str
    state: str
    priority: int
    ts: float = field(default_factory=time.time)

    log_meta: dict[str, Any] = field(default_factory=dict)
    cluster_integrity: dict[str, Any] = field(default_factory=dict)

    streams: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "state": self.state,
            "priority": self.priority,
            "ts": self.ts,
            "log_meta": self.log_meta,
            "cluster_integrity": self.cluster_integrity,
            "streams": self.streams,
        }
