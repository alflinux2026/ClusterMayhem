# Diff map

## cluster/runtime/models.py
```diff
+ from __future__ import annotations
+ from dataclasses import dataclass, field
+ from enum import Enum
+ from typing import Any, Optional
+ from uuid import uuid4
+ import time
+ class EventStatus(str, Enum):
+ class NodeState(str, Enum):
+ @dataclass(frozen=True, slots=True)
+ class StreamKey:
+     def stream_id(self) -> str:
+     def path_parts(self) -> list[str]:
+ @dataclass(slots=True)
+ class EventEnvelope:
+     def add_hop(self, hop: str) -> None:
+     def mark_status(self, status: EventStatus) -> None:
+     def mark_received(self) -> None:
+ @dataclass(slots=True)
+ class SegmentMeta:
```

## cluster/runtime/serialization.py
```diff
+ from __future__ import annotations
+ from dataclasses import asdict
+ from typing import Any
+ from .models import EventEnvelope, EventStatus, HeartbeatState, SegmentMeta, StreamKey, NodeRuntimeState
+ def event_to_record(event: EventEnvelope) -> dict[str, Any]:
+ def record_to_event(record: dict[str, Any]) -> EventEnvelope:
+ def segment_meta_to_record(meta: SegmentMeta) -> dict[str, Any]:
+ def heartbeat_to_record(hb: HeartbeatState) -> dict[str, Any]:
```

## cluster/runtime/paths.py
```diff
+ from __future__ import annotations
+ from pathlib import Path
+ from .models import SegmentMeta, StreamKey
+ def stream_dir(stream: StreamKey) -> Path:
+ def current_log_path(stream: StreamKey) -> Path:
+ def segments_dir(stream: StreamKey) -> Path:
+ def segment_log_path(stream: StreamKey, segment_id: str) -> Path:
+ def segment_meta_path(stream: StreamKey, segment_id: str) -> Path:
+ def build_segment_file_name(meta: SegmentMeta) -> str:
```

## cluster/runtime/heartbeat_builder.py
```diff
+ from __future__ import annotations
+ from typing import Any
+ import os
+ import time
+ import hashlib
+ from .models import HeartbeatState
+ def file_sha256(path: str, blocksize: int = 65536) -> str | None:
+ def build_heartbeat(node_id: str, state: str, priority: int, log_meta: dict[str, Any] | None = None, cluster_integrity: dict[str, Any] | None = None, streams: dict[str, dict[str, Any]] | None = None) -> HeartbeatState:
```

## cluster/runtime/noderuntime.py
```diff
+ from __future__ import annotations
+ import time
+ from typing import Any
+ from cluster.runtime.state import NodeState
+ from cluster.runtime.models import NodeRuntimeState
+ from cluster.runtime.eventlog import getlastappendmeta
+ from cluster.runtime.integrity import clusterintegrityreport, filesha256
+ class NodeRuntime:
+     def __init__(self, nodeid: str, priority: int):
+     def state(self) -> NodeState:
+     def state(self, newstate: NodeState) -> None:
+     def transition(self, newstate: NodeState) -> None:
+     def tick(self) -> None:
+     def build_log_meta(self, log_path: str) -> dict[str, Any]:
+     def build_heartbeat(self, log_path: str, streams: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
```

## cluster/runtime/apiapp.py
```diff
+ from __future__ import annotations
+ import os
+ import time
+ import logging
+ import requests
+ from fastapi import FastAPI, Request
+ from fastapi.responses import FileResponse, PlainTextResponse
+ from cluster.runtime.clusterstore import clusterstate
+ from cluster.runtime.leader import computeleader
+ from cluster.runtime.registry import CLUSTERREGISTRY
+ from cluster.runtime.eventlog import replayevents, getlocallogpath, getreplicalogpath, writereplicalog
+ from cluster.runtime.ingest import ingestevent
+ from cluster.runtime.events.clusterevent import ClusterEvent
+ from cluster.runtime import context as ctx
+ from cluster.runtime.worker.eventworker import executeevent
+ from cluster.runtime.state import NodeState
+ from cluster.runtime.models import HeartbeatState
+ def logdump():
+ def logdumplocal():
+ def logdumpreplica(nodeid: str):
+ def executeendpoint(event: ClusterEvent):
+ def ackevent(event: ClusterEvent):
+ def replay():
+     def handle(event):
```

## cluster/runtime/eventlog.py
```diff
+ from __future__ import annotations
+ import json
+ import os
+ from pathlib import Path
+ from typing import Any, Dict, List, Optional
+ from cluster.runtime.models import EventEnvelope, EventStatus, SegmentMeta, StreamKey
+ from cluster.runtime.serialization import event_to_record, record_to_event, segment_meta_to_record
+ def ensuredir() -> None:
+ def stream_dir(stream: StreamKey) -> Path:
+ def current_log_path(stream: StreamKey) -> Path:
+ def segments_dir(stream: StreamKey) -> Path:
+ def segment_log_path(stream: StreamKey, segment_id: str) -> Path:
+ def segment_meta_path(stream: StreamKey, segment_id: str) -> Path:
+ def state_path(stream: StreamKey) -> Path:
+ def getlocallogpath(stream: StreamKey | None = None) -> str:
+ def getreplicalogpath(nodeid: str) -> str:
+ def listreplicalogpaths() -> List[str]:
+ def loadeventsfrompath(path: str) -> List[dict]:
+ def writetextatomic(path: str, content: str) -> None:
```

## cluster/runtime/dispatcher.py
```diff
+ from __future__ import annotations
+ import time
+ from typing import Iterable
+ from cluster.runtime import context as ctx
+ from cluster.runtime.eventlog import getcreatedevents, getcompletedeventids, append_event
+ from cluster.runtime.eventrouter import forwardevent
+ from cluster.runtime.leader import computeleader, computealive
+ from cluster.runtime.models import EventEnvelope, EventStatus
+ from cluster.utils.logprint import logstate
+ def _iter_created_events() -> list[EventEnvelope]:
+ def dispatchtick() -> None:
+ def dispatchcreatedevent(event: EventEnvelope) -> None:
```

## cluster/runtime/reconciler_loop.py
```diff
+ from __future__ import annotations
+ import time
+ from collections import defaultdict
+ from cluster.runtime.eventlog import load_events, append_event
+ from cluster.runtime.models import EventEnvelope, EventStatus
+ def reconciletick(noderuntime) -> None:
```

## cluster/runtime/worker.py
```diff
+ from __future__ import annotations
+ from cluster.runtime.eventlog import append_event
+ from cluster.runtime.models import EventEnvelope, EventStatus
+ from cluster.utils.logprint import logstate
+ def runbusinesslogic(payload: dict) -> dict:
+ def executeevent(event: EventEnvelope):
```

## cluster/runtime/eventrouter.py
```diff
+ from __future__ import annotations
+ import requests
+ from cluster.runtime.registry import CLUSTERREGISTRY
+ from cluster.utils.logprint import logstate
+ from cluster.runtime.models import EventEnvelope
+ from cluster.runtime.eventlog import append_event
+ from cluster.runtime.events.eventstate import EventStatus
+ def forwardevent(nodeid: str, event: EventEnvelope):
```

## cluster/runtime/nodeworker.py
```diff
+ from __future__ import annotations
+ import threading
+ import time
+ from cluster.runtime.dispatcher import dispatchtick
+ from cluster.runtime.reconciler.reconcilerloop import reconciletick
+ from cluster.runtime.state import NodeState
+ from cluster.runtime import context as ctx
+ from cluster.runtime.logreplication import replicatelocal
+ class NodeWorker:
+     def __init__(self, node, peers, interval=1.0):
+     def start(self):
+     def stop(self):
+     def tickstandby(self):
+     def tickactive(self):
+     def tickdegraded(self):
+     def tickbystate(self):
+     def loop(self):
```
