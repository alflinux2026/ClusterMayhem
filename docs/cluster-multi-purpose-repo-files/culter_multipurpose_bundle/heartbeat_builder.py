from __future__ import annotations

from typing import Any
import os
import time
import hashlib

from .models import HeartbeatState


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


def build_heartbeat(node_id: str, state: str, priority: int, log_meta: dict[str, Any] | None = None, cluster_integrity: dict[str, Any] | None = None, streams: dict[str, dict[str, Any]] | None = None) -> HeartbeatState:
    return HeartbeatState(
        node_id=node_id,
        state=state,
        priority=priority,
        ts=time.time(),
        log_meta=log_meta or {},
        cluster_integrity=cluster_integrity or {},
        streams=streams or {},
    )
