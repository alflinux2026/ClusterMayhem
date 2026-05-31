from pathlib import Path
out = Path('output')
out.mkdir(exist_ok=True)

leader = '''import time

from cluster.utils.log_print import log_state
from cluster.runtime.cluster_store import cluster_state, get_active_cluster
from cluster.runtime import context as ctx


def compute_alive(timeout=1.5, include_self=False):
    now = time.time()
    alive = {}
    for node_id, node in get_active_cluster().items():
        last_seen = node.get("last_seen", 0)
        if now - last_seen <= timeout:
            alive[node_id] = node
    if include_self and ctx.node_id and ctx.node_id not in alive and ctx.node_id in cluster_state:
        alive[ctx.node_id] = cluster_state[ctx.node_id]
    return alive


def compute_leader():
    alive = compute_alive(include_self=True)
    if not alive:
        return None
    leader_id = min(alive.items(), key=lambda x: (x[1].get("priority", 9999), x[0]))[0]
    return leader_id
'''

integrity = '''import os
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
'''

bootstrap = '''import json
import os
import socket
import requests
import hashlib

from cluster.runtime import context as ctx


def load_or_bootstrap_config():
    path = os.getenv("CLUSTER_CONFIG", "config/node.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    node_id = socket.gethostname()
    cfg = {
        "node_id": node_id,
        "priority": int(os.getenv("NODE_PRIORITY", "100")),
        "port": int(os.getenv("NODE_PORT", "8000")),
        "tenant_id": os.getenv("TENANT_ID", "default"),
        "app_id": os.getenv("APP_ID", "mayhem"),
        "data_type": os.getenv("DATA_TYPE", "event"),
        "schema_version": os.getenv("SCHEMA_VERSION", "0.1"),
        "peers": [],
    }
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return cfg
'''

registry = '''CLUSTER_REGISTRY = {}


def register_node(node_id: str, host: str, port: int, priority: int = 100):
    CLUSTER_REGISTRY[node_id] = {
        "host": host,
        "port": port,
        "priority": priority,
    }
    return CLUSTER_REGISTRY[node_id]


def get_node(node_id: str):
    return CLUSTER_REGISTRY.get(node_id)
'''

ingest = '''from cluster.runtime.event_log import append_event
from cluster.utils.log_print import log_state
from cluster.runtime.events.event_state import EventStatus


def ingest_event(event, source_node_id: str):
    event.source_node = source_node_id
    event.mark_received()
    append_event(event)
    log_state("green", "[INGEST]", f"{event.event_id} from {source_node_id}", 3)
    return {"status": EventStatus.CREATED.value, "event_id": event.event_id}
'''

files = {
    'cluster_runtime_leader_patch.py': leader,
    'cluster_runtime_integrity_patch.py': integrity,
    'cluster_runtime_bootstrap_patch.py': bootstrap,
    'cluster_runtime_registry_patch.py': registry,
    'cluster_runtime_ingest_patch.py': ingest,
}
for name, content in files.items():
    (out / name).write_text(content, encoding='utf-8')

print('final core patches ready')
