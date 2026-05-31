import json
import os
import hashlib
from typing import Any

from cluster.runtime import context as ctx
from cluster.runtime.cluster_store import cluster_state
from cluster.runtime.event_log import get_local_log_path, get_last_append_meta
from cluster.runtime.leader import compute_alive

IGNORED_NODE_KEYS = {"last_seen"}
IGNORED_LOG_META_KEYS = set()


def file_sha256(path: str, block_size: int = 65536) -> str | None:
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(block_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def canonicalize(obj: Any, ignored_keys: set[str] | None = None) -> Any:
    ignored_keys = ignored_keys or set()
    if isinstance(obj, dict):
        return {k: canonicalize(v, ignored_keys) for k, v in sorted(obj.items()) if k not in ignored_keys}
    if isinstance(obj, list):
        return [canonicalize(v, ignored_keys) for v in obj]
    return obj


def compare_views(a: dict, b: dict) -> bool:
    return canonicalize(a, IGNORED_NODE_KEYS) == canonicalize(b, IGNORED_NODE_KEYS)


def local_integrity_api() -> dict:
    path = get_local_log_path()
    alive = compute_alive(include_self=True)
    cluster_view = canonicalize(cluster_state, IGNORED_NODE_KEYS)
    peer_views = {node_id: canonicalize(data, IGNORED_NODE_KEYS) for node_id, data in alive.items()}

    self_view = canonicalize(cluster_state.get(ctx.node_id, {}), IGNORED_NODE_KEYS)
    local_log_meta = {
        "path": path,
        "size": os.path.getsize(path) if os.path.exists(path) else 0,
        "sha256": file_sha256(path),
    }

    return {
        "node_id": ctx.node_id,
        "alive_nodes": sorted(alive.keys()),
        "self_view": self_view,
        "cluster_view": cluster_view,
        "peer_views": peer_views,
        "local_log_meta": local_log_meta,
        "last_append_meta": get_last_append_meta(),
        "integrity_ok": True,
    }


def cluster_integrity_report() -> dict:
    alive = compute_alive(include_self=True)
    cluster_view = canonicalize(cluster_state, IGNORED_NODE_KEYS)
    reference = canonicalize(cluster_state, IGNORED_NODE_KEYS)
    per_peer = {}
    for node_id, data in alive.items():
        per_peer[node_id] = {
            "matches_reference": canonicalize(data, IGNORED_NODE_KEYS) == reference.get(node_id, {}),
            "view": canonicalize(data, IGNORED_NODE_KEYS),
        }

    return {
        "node_id": ctx.node_id,
        "alive_nodes": sorted(alive.keys()),
        "cluster_view": cluster_view,
        "reference": reference,
        "per_peer": per_peer,
        "integrity_ok": all(v["matches_reference"] for v in per_peer.values()),
    }
