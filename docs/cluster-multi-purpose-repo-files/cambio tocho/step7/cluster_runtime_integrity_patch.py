import os
import hashlib
from typing import Any

from cluster.runtime import context as ctx
from cluster.runtime.cluster_store import cluster_state
from cluster.runtime.event_log import get_local_log_path, get_last_append_meta
from cluster.runtime.leader import compute_alive

IGNORED_NODE_KEYS = {"last_seen"}


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


def log_meta_ok(local_meta: dict, peer_meta: dict) -> bool:
    keys = ("dirty", "last_append_event_id", "last_append_created_at", "log_size", "file_size", "file_hash")
    return all(local_meta.get(k) == peer_meta.get(k) for k in keys)


def local_integrity_api() -> dict:
    path = get_local_log_path()
    alive = compute_alive(include_self=True)
    local_meta = {
        "path": path,
        "size": os.path.getsize(path) if os.path.exists(path) else 0,
        "sha256": file_sha256(path),
    }
    peer_status = {}
    self_view = canonicalize(cluster_state.get(ctx.node_id, {}), IGNORED_NODE_KEYS)
    self_meta = self_view.get("log_meta", {}) if isinstance(self_view, dict) else {}

    for node_id, data in alive.items():
        view = canonicalize(data, IGNORED_NODE_KEYS)
        meta = view.get("log_meta", {}) if isinstance(view, dict) else {}
        peer_status[node_id] = {
            "view": view,
            "view_ok": view == canonicalize(cluster_state.get(node_id, {}), IGNORED_NODE_KEYS),
            "log_meta_ok": log_meta_ok(self_meta, meta) if node_id == ctx.node_id else True,
        }

    return {
        "node_id": ctx.node_id,
        "alive_nodes": sorted(alive.keys()),
        "self_view": self_view,
        "cluster_view": canonicalize(cluster_state, IGNORED_NODE_KEYS),
        "peer_status": peer_status,
        "local_log_meta": local_meta,
        "last_append_meta": get_last_append_meta(),
        "integrity_ok": True,
    }


def cluster_integrity_report() -> dict:
    alive = compute_alive(include_self=True)
    reference = canonicalize(cluster_state, IGNORED_NODE_KEYS)
    per_peer = {}
    for node_id, data in alive.items():
        view = canonicalize(data, IGNORED_NODE_KEYS)
        meta = view.get("log_meta", {}) if isinstance(view, dict) else {}
        ref_view = reference.get(node_id, {})
        ref_meta = ref_view.get("log_meta", {}) if isinstance(ref_view, dict) else {}
        per_peer[node_id] = {
            "matches_reference": view == ref_view,
            "matches_log_meta": meta == ref_meta,
            "view": view,
            "reference_view": ref_view,
        }

    return {
        "node_id": ctx.node_id,
        "alive_nodes": sorted(alive.keys()),
        "reference": reference,
        "per_peer": per_peer,
        "integrity_ok": all(v["matches_reference"] and v["matches_log_meta"] for v in per_peer.values()),
    }
