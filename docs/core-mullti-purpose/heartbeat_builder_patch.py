from __future__ import annotations

from typing import Any
import os
import time
import hashlib

from cluster.runtime.models import HeartbeatState, NodeRuntimeState
from cluster.runtime.state import NodeState


def file_sha256(path: str, blocksize: int = 65536) -> str | None:
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(blocksize)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def build_heartbeat(runtime_state: NodeRuntimeState, log_path: str, streams: dict[str, dict[str, Any]] | None = None) -> HeartbeatState:
    size = os.path.getsize(log_path) if os.path.exists(log_path) else 0
    log_meta = {
        "dirty": runtime_state.log_meta.get("dirty", False),
        "last_append_event_id": runtime_state.log_meta.get("last_append_event_id"),
        "last_append_created_at": runtime_state.log_meta.get("last_append_created_at"),
        "log_size": size,
        "file_size": size,
        "file_hash": file_sha256(log_path),
    }
    runtime_state.log_meta = log_meta
    return HeartbeatState(
        node_id=runtime_state.node_id,
        state=runtime_state.state.value if isinstance(runtime_state.state, NodeState) else str(runtime_state.state),
        priority=runtime_state.priority,
        ts=time.time(),
        log_meta=log_meta,
        cluster_integrity=runtime_state.cluster_integrity,
        streams=streams or runtime_state.active_streams,
    )
