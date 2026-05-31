import json
import os
import hashlib
from typing import Any, Dict, Tuple

from cluster.runtime import context as ctx
from cluster.runtime.cluster_store import cluster_state
from cluster.runtime.event_log import get_last_append_meta, get_local_log_path
from cluster.runtime.leader import compute_alive

IGNORE_NODE_KEYS = {"last_seen"}
IGNORE_META_KEYS = set()


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


def canonicalize(obj: Any, ignore_keys: set[str] | None = None) -> Any:
    ignore_keys = ignore_keys or set()
    if isinstance(obj, dict):
        return {k: canonicalize(v, ignore_keys) for k, v in sorted(obj.items()) if k not in ignore_keys}
    if isinstance(obj, list):
        return [canonicalize(v, ignore_keys) for v in obj]
    return obj


def node_view(node_id: str) -> dict:
    data = cluster_state.get(node_id, {})
    out = canonicalize(data, IGNORE_NODE_KEYS)
    if isinstance(out, dict):
        out.setdefault("log_meta", {})
        if isinstance(out["log_meta"], dict):
            out["log_meta"] = canonicalize(out["log_meta"], IGNORE_META_KEYS)
    return out


def local_integrity_snapshot() -> dict:
    path = get_local_log_path()
    return {
        "node_id": ctx.node_id,
        "state": getattr(getattr(ctx, "node", None), "state", None).value if getattr(ctx, "node", None) else None,
        "priority": getattr(getattr(ctx, "node", None), "priority", None),
        "alive_peers": sorted(compute_alive(include_self=True).keys()),
        "cluster_view": canonicalize(cluster_state, IGNORE_NODE_KEYS),
        "local_log_path": path,
        "local_log_size": os.path.getsize(path) if os.path.exists(path) else 0,
        "local_log_hash": file_sha256(path),
        "last_append_meta": get_last_append_meta(),
    }


def check_cluster_integrity() -> dict:
    alive = compute_alive(include_self=True)
    cluster_view = canonicalize(cluster_state, IGNORE_NODE_KEYS)
    peers = {}
    for node_id, data in alive.items():
        peers[node_id] = {
            "view": canonicalize(data, IGNORE_NODE_KEYS),
            "log_meta": canonicalize(data.get("log_meta", {}), IGNORE_META_KEYS),
        }
    reference = canonicalize(cluster_state, IGNORE_NODE_KEYS)
    return {
        "node_id": ctx.node_id,
        "alive_nodes": sorted(alive.keys()),
        "cluster_view": cluster_view,
        "peer_views": peers,
        "reference": reference,
        "self_view": node_view(ctx.node_id),
    }
