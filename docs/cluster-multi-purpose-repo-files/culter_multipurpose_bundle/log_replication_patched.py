import logging
import os
import time
import requests

from cluster.runtime import context as ctx
from cluster.runtime.cluster_store import cluster_state
from cluster.runtime.registry import CLUSTER_REGISTRY
from cluster.runtime.event_log import (
    read_local_log_text,
    write_replica_log,
    get_replica_log_path,
    read_state,
    clear_state,
)
from cluster.utils.log_print import log_state

logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("requests").setLevel(logging.ERROR)

PEERALIVETTLSEC = 3.0


def canonical_replica_node_id() -> str:
    return ctx.node_id


def alive_peer_ids():
    out = []
    now = time.time()
    for node_id, data in cluster_state.items():
        if node_id == ctx.node_id:
            continue
        if now - data.get("last_seen", 0) > PEERALIVETTLSEC:
            continue
        out.append(node_id)
    return out


def _sig(path: str):
    try:
        st = os.stat(path)
        return st.st_mtime_ns, st.st_size
    except FileNotFoundError:
        return None


def replicate_local():
    node_id = canonical_replica_node_id()

    log_state("cyan", "REPL TICK", f"node={node_id}", 3)

    allowed_states = {"ACTIVE", "STANDBY", "DEGRADED"}
    node_state = getattr(getattr(ctx, "node", None), "state", None)
    node_state_value = getattr(node_state, "value", None)
    log_state("cyan", "REPL STATE", f"state={node_state_value} allowed={node_state_value in allowed_states}", 3)
    if node_state_value not in allowed_states:
        return

    state = read_state()
    dirty = bool(state.get("dirty", False))
    log_state("cyan", "REPL FLAG", f"dirty={dirty} state_exists={bool(state)}", 3)
    if not dirty:
        return

    content = read_local_log_text()
    content_bytes = content.encode("utf-8") if content else b""
    log_state("cyan", "REPL CONTENT", f"len={len(content_bytes)} empty={not content.strip()}", 3)
    if not content.strip():
        log_state("yellow", "REPL SKIP", "empty content", 3)
        return

    replica_path = get_replica_log_path(node_id)
    local_sig = _sig(get_replica_log_path(node_id) + ".tmp")
    remote_sig = _sig(replica_path)
    if remote_sig is not None and remote_sig == _sig(replica_path) and len(content_bytes) == remote_sig[1]:
        log_state("yellow", "REPL SKIP", "already synced", 3)
        return

    write_replica_log(node_id, content)
    local_written_bytes = len(content_bytes)
    log_state("cyan", "REPL WRITE", f"bytes={local_written_bytes}", 3)

    peers = alive_peer_ids()
    log_state("cyan", "REPL PEERS", f"peers={peers}", 3)
    if not peers:
        log_state("yellow", "REPL SKIP", "no peers", 3)
        return

    success = True
    for peer_id in peers:
        node = CLUSTER_REGISTRY.get(peer_id)
        if not node:
            log_state("red", "LOG REPL FAIL", f"{peer_id} missing registry", 3)
            success = False
            continue

        url = f"http://{node['host']}:{node['port']}/debug/log/replica/{node_id}"
        log_state("cyan", "REPL POST", f"peer={peer_id} url={url}", 3)
        try:
            resp = requests.post(
                url,
                data=content_bytes,
                headers={"Content-Type": "text/plain; charset=utf-8"},
                timeout=2,
            )
            if not resp.ok:
                success = False
                log_state("red", "LOG REPL FAIL", f"{peer_id} status={resp.status_code}", 3)
                continue

            data = resp.json()
            ok = bool(data.get("ok"))
            peer_written = data.get("written_bytes")
            peer_path = data.get("path")

            if ok and peer_written == local_written_bytes:
                log_state("cyan", "LOG REPL", f"{node_id} -> {peer_id}", 3)
            else:
                success = False
                log_state(
                    "red",
                    "LOG REPL FAIL",
                    f"{peer_id} path={peer_path} bytes={peer_written} expected={local_written_bytes}",
                    3,
                )

        except Exception as e:
            success = False
            log_state("red", "LOG REPL FAIL", f"{peer_id} err={e}", 3)

    if success:
        clear_state()
        log_state("cyan", "REPL CLEAR", "dirty=false", 3)
