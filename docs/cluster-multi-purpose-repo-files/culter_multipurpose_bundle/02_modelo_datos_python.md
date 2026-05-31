# Culter Multi Purpose — Modelo de datos Python

## StreamKey
```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class StreamKey:
    tenant_id: str
    app_id: str
    data_type: str
    schema_version: str = "v1"

    def stream_id(self) -> str:
        return f"{self.tenant_id}.{self.app_id}.{self.data_type}.{self.schema_version}"
```

## EventEnvelope
```python
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import uuid4
import time

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
```

## SegmentMeta
```python
from dataclasses import dataclass, field
from typing import Optional
import time

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
```

## HeartbeatState
```python
from dataclasses import dataclass, field
from typing import Any
import time

@dataclass(slots=True)
class HeartbeatState:
    node_id: str
    state: str
    priority: int
    ts: float = field(default_factory=time.time)
    log_meta: dict[str, Any] = field(default_factory=dict)
    cluster_integrity: dict[str, Any] = field(default_factory=dict)
    streams: dict[str, dict[str, Any]] = field(default_factory=dict)
```

## NodeState
```python
from dataclasses import dataclass, field
from typing import Any
import time

@dataclass(slots=True)
class NodeState:
    node_id: str
    state: str
    priority: int
    last_seen: float = field(default_factory=time.time)
    log_meta: dict[str, Any] = field(default_factory=dict)
    cluster_integrity: dict[str, Any] = field(default_factory=dict)
    active_streams: dict[str, dict[str, Any]] = field(default_factory=dict)
```
