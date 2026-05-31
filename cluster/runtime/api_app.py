# File: ./cluster/runtime/api_app.py
# Previous: none
# Author: alftorres
# Date: 2026-05-28T17:05:50+0200
# Version: 0.0.0
# Genealogy:
#   ./cluster/runtime/api_app.py 0.0.0 2026-05-28T17:05:50+0200
#   God
#
# Purpose:
#   API HTTP del nodo del cluster (FastAPI).
#   Expone endpoints para: recibir eventos, heartbeats, watchdogs, debug de logs,
#   ver estado del cluster, leader election, integridad, y comando de sleep/revive.
#   Se sirve con uvicorn en node_boot.py.
# Notes:
#   - POST /event: recibe eventos y los reenvía al líder si soy standby
#   - POST /heartbeat: actualiza cluster_state con estado del nodo
#   - POST /watchdog: actualiza last_watchdog para detectar nodos bloqueados
#   - GET /cluster: estado completo del cluster
#   - GET /leader: node_id del líder actual
#   - GET /health: health check del nodo local
#   - GET /debug/*: endpoints de debugging (logs, eventos, replicas)
#   - POST /sleep: transiciona a ISOLATED (pausa)
#   - POST /revive: transiciona a BOOT (reanuda)
#   - Todos los endpoints checkean estado ISOLATED y retornan error si está aislado
#
# FRV-ID: a4b1ac60fe9e322b
# Header_End

import json
import logging
import os
import time
from collections import Counter
from pathlib import Path

import requests
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from cluster.runtime import context as ctx
from cluster.runtime.cluster_store import cluster_state
from cluster.runtime.event_log import (
    get_local_log_path,
    get_replica_log_path,
    get_replica_events_path,
    get_completed_log_path,
    replay_events,
    write_replica_log,
    write_replica_events,
)
from cluster.runtime.events.cluster_event import ClusterEvent
from cluster.runtime.event_log import ingest_event
from cluster.runtime.integrity import cluster_integrity_report, local_integrity_api
from cluster.runtime.leader import compute_leader
from cluster.runtime.node_runtime import NodeState
from cluster.runtime.registry import CLUSTER_REGISTRY
from cluster.utils.log_print import log_state

logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("requests").setLevel(logging.ERROR)

# =============================================================================
# Aplicación FastAPI
# =============================================================================

#: Aplicación FastAPI principal
app = FastAPI()


class Heartbeat(BaseModel):
    """
    Modelo de heartbeat enviado por los nodos.

    Attributes:
        node_id: ID del nodo.
        state: Estado actual (BOOT, STANDBY, ACTIVE, etc.).
        priority: Prioridad para leader election.
        state_since: Timestamp cuando se entró al estado.
        prev_state: Estado anterior.
        state_reason: Razón de la última transición.
        log_meta: Metadatos del log (dirty, last_append_event_id, etc.).
        cluster_integrity: Reporte de integridad.
        streams: Stats de eventos (counts, totals).
    """
    node_id: str
    state: str
    priority: int
    state_since: float | None = None
    prev_state: str | None = None
    state_reason: str | None = None
    log_meta: dict | None = None
    cluster_integrity: dict | None = None
    streams: dict | None = None


class Watchdog(BaseModel):
    """
    Modelo de watchdog enviado por los nodos.

    Attributes:
        node_id: ID del nodo.
        busy: True si el nodo está ocupado procesando.
        emitted_at: Timestamp cuando se emitió.
    """
    node_id: str
    busy: bool = True
    emitted_at: float | None = None


class SegmentRotateRequest(BaseModel):
    """
    Modelo para rotación de segmentos.

    Attributes:
        request_id: ID único de la request.
        source_node: Nodo origen.
        target_group: Grupo destino.
        segment: Segmento a rotar (default: "000").
        files: Lista de tipos de archivos (default: ["events", "event_log"]).
        action: Acción a realizar (default: "rotate").
        force: Si True, crea entry incluso si el archivo no existe.
        ts: Timestamp opcional.
    """
    request_id: str
    source_node: str
    target_group: str
    segment: str
    files: list[str] = ["events", "event_log"]
    action: str = "rotate"
    force: bool = False
    ts: float | None = None


def _round_or_none(value: float | None, digits: int = 1) -> float | None:
    """Redondea un valor o retorna None si es None/inválido."""
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except Exception:
        return None


def _watchdog_age_s(node: dict, now: float | None = None) -> float | None:
    """Calcula cuántos segundos desde el último watchdog."""
    now = now or time.time()
    last_watchdog = node.get("last_watchdog")
    if last_watchdog is None:
        return None
    try:
        return max(0.0, now - float(last_watchdog))
    except Exception:
        return None


def _state_age_s(node: dict, now: float | None = None) -> float | None:
    """Calcula cuántos segundos desde que se entró al estado actual."""
    now = now or time.time()
    state_since = node.get("state_since")
    if state_since is None:
        return None
    try:
        return max(0.0, now - float(state_since))
    except Exception:
        return None


def _seen_age_s(node: dict, now: float | None = None) -> float | None:
    """Calcula cuántos segundos desde el último last_seen."""
    now = now or time.time()
    last_seen = node.get("last_seen")
    if last_seen is None:
        return None
    try:
        return max(0.0, now - float(last_seen))
    except Exception:
        return None


def _presence_age_s(node: dict, now: float | None = None) -> float | None:
    """Calcula cuántos segundos desde la última actividad (last_seen o last_watchdog)."""
    now = now or time.time()
    last_seen = node.get("last_seen")
    last_watchdog = node.get("last_watchdog")
    candidates = []
    for value in (last_seen, last_watchdog):
        if value is None:
            continue
        try:
            candidates.append(float(value))
        except Exception:
            continue
    if not candidates:
        return None
    return max(0.0, now - max(candidates))


def _presence_health(node: dict, now: float | None = None, stale_after_s: float = 3.0) -> str:
    """
    Calcula la salud de presencia del nodo.

    Returns:
        str: "ok" si actividad reciente (< stale_after_s), "stale" si no.
    """
    age = _presence_age_s(node, now)
    if age is None:
        return "stale"
    return "ok" if age < stale_after_s else "stale"


def _compact_node(node: dict) -> dict:
    """
    Compacta un nodo a un resúmen para el dashboard.

    Args:
        node: Dict completo del nodo.

    Returns:
        dict: Node compactado con state, priority, ages, health, etc.
    """
    now = time.time()
    return {
        "state": node.get("state"),
        "priority": node.get("priority"),
        "last_seen": node.get("last_seen"),
        "seen_age_s": _round_or_none(_seen_age_s(node, now), 3),
        "last_watchdog": node.get("last_watchdog"),
        "watchdog_age_s": _round_or_none(_watchdog_age_s(node, now), 3),
        "watchdog_busy": node.get("watchdog_busy"),
        "presence_age_s": _round_or_none(_presence_age_s(node, now), 3),
        "presence_health": _presence_health(node, now),
        "state_since": node.get("state_since"),
        "state_age_s": _round_or_none(_state_age_s(node, now), 3),
        "prev_state": node.get("prev_state"),
        "state_reason": node.get("state_reason"),
        "log_meta": node.get("log_meta", {}),
        "streams": node.get("streams", {}),
    }


def _read_jsonl(path: str) -> list[dict]:
    """Carga eventos de un archivo JSONL."""
    if not os.path.exists(path):
        return []
    out: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def _summarize_events(events: list[dict]) -> dict:
    """
    Crea un resúmen de eventos con counts por status.

    Args:
        events: Lista de eventos (puede tener duplicados por event_id).

    Returns:
        dict: Resúmen con total_events, counts (created, executing, completed), last_event_id.
    """
    latest_by_event_id: dict[str, dict] = {}
    last_event_id = None
    for event in events:
        event_id = event.get("event_id")
        if not event_id:
            continue
        latest_by_event_id[event_id] = event
        last_event_id = event_id
    counts = Counter()
    for event in latest_by_event_id.values():
        status = str(event.get("status", "unknown")).lower()
        counts[status] += 1
    return {
        "total_events": len(latest_by_event_id),
        "counts": {
            "created": counts.get("created", 0),
            "executing": counts.get("executing", 0),
            "completed": counts.get("completed", 0),
            "unknown": counts.get("unknown", 0),
        },
        "last_event_id": last_event_id,
    }


def _next_rotation_index(base_dir, stem, suffix=".jsonl"):
    """Encuentra el próximo índice disponible para rotación de archivos."""
    base_dir = Path(base_dir)
    idx = 1
    while True:
        candidate = base_dir / f"{stem}.{idx:03d}{suffix}"
        if not candidate.exists():
            return idx
        idx += 1


def rotate_segment_files(target_group: str, segment: str = "000", files=None, force: bool = False):
    """Rota archivos de segmento (renombra .local.000.jsonl a .{target_group}.001.jsonl)."""
    files = files or ["events", "event_log"]
    base_dir = Path(get_local_log_path(None)).resolve().parent
    result = {}

    for kind in files:
        src = base_dir / f"{kind}.local.{segment}.jsonl"
        if not src.exists():
            if force:
                result[kind] = {"before": str(src), "after": None, "index": None, "forced": True}
                continue
            raise FileNotFoundError(str(src))

        idx = _next_rotation_index(base_dir, f"{kind}.{target_group}")
        dst = base_dir / f"{kind}.{target_group}.{idx:03d}.jsonl"
        os.replace(str(src), str(dst))
        result[kind] = {"before": str(src), "after": str(dst), "index": idx, "forced": False}

    return result


def cleanup_local_segment_files(target_group: str, segment: str = "000", files=None):
    """Elimina archivos de segmento local después de rotar."""
    files = files or ["events", "event_log"]
    base_dir = Path(get_local_log_path(None)).resolve().parent
    removed = []
    already_gone = []

    for kind in files:
        p = base_dir / f"{kind}.local.{segment}.jsonl"
        if p.exists():
            p.unlink()
            removed.append(str(p))
        else:
            already_gone.append(str(p))

    return {"target_group": target_group, "segment": segment, "removed": removed, "already_gone": already_gone}


# =============================================================================
# Endpoints de debug (logs)
# =============================================================================

@app.get("/debug/log")
def log_dump():
    """Devuelve el contenido del log local."""
    path = get_local_log_path(getattr(ctx, "stream", None))
    if not os.path.exists(path):
        return PlainTextResponse("", status_code=200)
    return FileResponse(path, media_type="text/plain")


@app.get("/debug/log/local")
def log_dump_local():
    """Alias de /debug/log."""
    path = get_local_log_path(getattr(ctx, "stream", None))
    if not os.path.exists(path):
        return PlainTextResponse("", status_code=200)
    return FileResponse(path, media_type="text/plain")


@app.get("/debug/log/completed")
def log_dump_completed():
    """Devuelve el contenido del log de eventos completados."""
    path = get_completed_log_path(getattr(ctx, "stream", None))
    if not os.path.exists(path):
        return PlainTextResponse("", status_code=200)
    return FileResponse(path, media_type="text/plain")


@app.get("/debug/log/replica/{node_id}")
def log_dump_replica(node_id: str):
    """Devuelve el contenido del log replica de un peer."""
    path = get_replica_log_path(node_id)
    if not os.path.exists(path):
        return PlainTextResponse("", status_code=404)
    return FileResponse(path, media_type="text/plain")


@app.get("/debug/log/replica_events/{node_id}")
def events_dump_replica(node_id: str):
    """Devuelve el contenido del events replica de un peer."""
    path = get_replica_events_path(node_id)
    if not os.path.exists(path):
        return PlainTextResponse("", status_code=404)
    return FileResponse(path, media_type="text/plain")


@app.post("/debug/log/replica/{node_id}")
async def log_replica_write(node_id: str, request: Request):
    """
    Recibe y escribe el log replica de un peer.

    Parte del mecanismo de replicación: el peer envía su log local
    y este endpoint lo guarda como replica.
    """
    try:
        content = await request.body()
    except Exception as e:
        return {"ok": False, "node_id": node_id, "error": str(e)}
    text = content.decode("utf-8") if content else ""
    write_replica_log(node_id, text)
    return {"ok": True, "node_id": node_id, "path": get_replica_log_path(node_id), "bytes": len(content)}


@app.post("/debug/events/replica/{node_id}")
async def events_replica_write(node_id: str, request: Request):
    """
    Recibe y escribe el events replica de un peer.

    Similar a log_replica_write() pero para eventos completados.
    """
    try:
        content = await request.body()
    except Exception as e:
        return {"ok": False, "node_id": node_id, "error": str(e)}
    text = content.decode("utf-8") if content else ""
    write_replica_events(node_id, text)
    return {"ok": True, "node_id": node_id, "path": get_replica_events_path(node_id), "bytes": len(content)}


# =============================================================================
# Endpoints de debug (eventos)
# =============================================================================

@app.get("/debug/events/summary")
def events_summary():
    """Devuelve un resúmen de eventos locales."""
    path = get_local_log_path(getattr(ctx, "stream", None))
    events = _read_jsonl(path)
    return {"node_id": ctx.node_id, "scope": "local", "path": path, **_summarize_events(events)}


@app.get("/debug/events/summary/replica/{node_id}")
def events_summary_replica(node_id: str):
    """Devuelve un resúmen de eventos de la replica de un peer."""
    path = get_replica_log_path(node_id)
    events = _read_jsonl(path)
    return {"node_id": ctx.node_id, "scope": "replica", "replica_of": node_id, "path": path, **_summarize_events(events)}


@app.get("/debug/events/summary/completed")
def events_summary_completed():
    """Devuelve un resúmen de eventos completados."""
    path = get_completed_log_path(getattr(ctx, "stream", None))
    events = _read_jsonl(path)
    return {"node_id": ctx.node_id, "scope": "completed", "path": path, **_summarize_events(events)}


# =============================================================================
# Endpoints de segmentación
# =============================================================================

@app.post("/segment/rotate")
def segment_rotate(req: SegmentRotateRequest):
    """
    Rota archivos de segmento.

    Si el nodo está en ISOLATED, retorna error.
    Si falla, retorna error con message.
    """
    if ctx.node.state == NodeState.ISOLATED:
        return {
            "request_id": req.request_id,
            "node_id": ctx.node_id,
            "source_node": req.source_node,
            "target_group": req.target_group,
            "segment": req.segment,
            "rotated": False,
            "files": {},
            "error": "node isolated",
            "ts": time.time(),
        }
    try:
        result = rotate_segment_files(
            target_group=req.target_group,
            segment=req.segment,
            files=req.files,
            force=req.force,
        )
        return {
            "request_id": req.request_id,
            "node_id": ctx.node_id,
            "source_node": req.source_node,
            "target_group": req.target_group,
            "segment": req.segment,
            "rotated": True,
            "files": result,
            "error": None,
            "ts": time.time(),
        }
    except Exception as e:
        return {
            "request_id": req.request_id,
            "node_id": ctx.node_id,
            "source_node": req.source_node,
            "target_group": req.target_group,
            "segment": req.segment,
            "rotated": False,
            "files": {},
            "error": str(e),
            "ts": time.time(),
        }


# =============================================================================
# Endpoints de eventos
# =============================================================================

@app.post("/ack")
def ack(event: ClusterEvent):
    """ACK de un evento (logging solo)."""
    log_state("green", "[ACK]", f"{event.event_id} received", 3)
    return {"ok": True, "event_id": event.event_id}


@app.post("/replay")
def replay():
    """Reproduce todos los eventos del log (llama a handler vacío)."""
    def handler(event):
        return None
    replay_events(handler, getattr(ctx, "stream", None))
    return {"ok": True}


@app.post("/event")
def handle_event(event: ClusterEvent):
    """
    Recibe un evento y lo ingiere o reenvía al líder.

    Flow:
        1. Checkea si el nodo está en SEGMENTATION/DRAINING/ISOLATED -> error
        2. Checkea si hay líder -> si no, error
        3. Si soy STANDBY, reenvío al líder con requests.post()
        4. Si soy líder, ingierto el evento con ingest_event()

    Args:
        event: Evento a ingerir.

    Returns:
        dict: {"status": "ok", "event_id": ..., "result": ...} si es líder
              o resp.json() del líder si soy standby
    """
    if ctx.node.state == NodeState.SEGMENTATION:
        return {"error": "node SEGMENTATION"}
    if ctx.node.state == NodeState.DRAINING:
        return {"error": "node DRAINING"}
    if ctx.node.state == NodeState.ISOLATED:
        return {"error": "node ISOLATED"}
    leader = compute_leader()
    if not leader:
        log_state("red", "(NO LEADER)", event.event_id, 3)
        return {"error": "no leader"}

    if ctx.node.state == NodeState.STANDBY:
        msg = event.payload.get("msg", "<no-msg>")
        log_state("cyan", "[EVENT FWD]", f"{msg:12} -> {leader}", 3)
        node = CLUSTER_REGISTRY[leader]
        url = f"http://{node['host']}:{node['port']}/event"
        try:
            resp = requests.post(url, json=event.model_dump(), timeout=2)
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    result = ingest_event(event, ctx.node_id)
    return {"status": "ok", "event_id": event.event_id, "result": result}


# =============================================================================
# Endpoints de control de estado
# =============================================================================

@app.post("/sleep")
def sleep():
    """
    Pone el nodo en ISOLATED (sleep/pausa).

    Transiciona a ISOLATED y retorna el nuevo estado.
    """
    log_state("red", "- SLEEP -", f"{ctx.node_id} -> SLEEP", 3)
    ctx.node.transition(NodeState.ISOLATED, reason="sleep_command")
    return {"ok": True, "node": ctx.node_id, "state": ctx.node.state.value, "state_since": getattr(ctx.node, "state_since", None), "prev_state": getattr(ctx.node, "prev_state", None), "state_reason": getattr(ctx.node, "state_reason", None)}


@app.post("/revive")
def revive():
    """
    Reanuda el nodo desde ISOLATED (wake-up).

    Transiciona a BOOT y retorna el nuevo estado.
    """
    log_state("red", "- WAKEUP -", f"{ctx.node_id} -> WAKEUP", 3)
    ctx.node.transition(NodeState.BOOT, reason="revive_command")
    return {"ok": True, "node": ctx.node_id, "state": ctx.node.state.value, "state_since": getattr(ctx.node, "state_since", None), "prev_state": getattr(ctx.node, "prev_state", None), "state_reason": getattr(ctx.node, "state_reason", None)}


# =============================================================================
# Endpoints de health y cluster
# =============================================================================

@app.get("/health")
def health():
    """
    Health check del nodo local.

    Returns:
        dict: Status ("ok" o "stale"), state, ages, watchdog info, sleeping flag.
    """
    local_entry = cluster_state.get(ctx.node_id, {})
    local_node = {
        "state_since": getattr(ctx.node, "state_since", None),
        "last_seen": local_entry.get("last_seen"),
        "last_watchdog": local_entry.get("last_watchdog"),
        "watchdog_busy": local_entry.get("watchdog_busy"),
    }
    return {
        "status": _presence_health(local_node),
        "node": ctx.node_id,
        "state": ctx.node.state.value,
        "state_since": getattr(ctx.node, "state_since", None),
        "state_age_s": _round_or_none(_state_age_s({"state_since": getattr(ctx.node, "state_since", None)}), 3),
        "last_seen": local_node.get("last_seen"),
        "seen_age_s": _round_or_none(_seen_age_s(local_node), 3),
        "last_watchdog": local_node.get("last_watchdog"),
        "watchdog_age_s": _round_or_none(_watchdog_age_s(local_node), 3),
        "watchdog_busy": local_node.get("watchdog_busy"),
        "presence_age_s": _round_or_none(_presence_age_s(local_node), 3),
        "sleeping": ctx.node.state == NodeState.ISOLATED,
    }


@app.get("/cluster")
def get_cluster():
    """Devuelve el estado completo del cluster (todos los nodos)."""
    return {node_id: _compact_node(node) for node_id, node in cluster_state.items()}


@app.get("/leader")
def get_leader():
    """Devuelve el node_id del líder actual."""
    return {"leader": compute_leader()}


@app.post("/watchdog")
def watchdog(wd: Watchdog):
    """
    Recibe un watchdog de un peer.

    Actualiza cluster_state con last_watchdog y watchdog_busy.
    """
    if ctx.node.state == NodeState.ISOLATED:
        return {"error": "node isolated"}
    existing = cluster_state.get(wd.node_id, {})
    ts = wd.emitted_at if wd.emitted_at is not None else time.time()
    cluster_state[wd.node_id] = {**existing, "last_watchdog": ts, "watchdog_busy": bool(wd.busy)}
    return {"ok": True, "node_id": wd.node_id, "last_watchdog": ts, "watchdog_busy": bool(wd.busy)}


@app.post("/heartbeat")
def heartbeat(hb: Heartbeat):
    """
    Recibe un heartbeat de un peer.

    Actualiza cluster_state con state, priority, last_seen, state_since, etc.
    """
    if ctx.node.state == NodeState.ISOLATED:
        return {"error": "node isolated"}
    existing = cluster_state.get(hb.node_id, {})
    cluster_state[hb.node_id] = {
        **existing,
        "state": hb.state,
        "priority": hb.priority,
        "last_seen": time.time(),
        "state_since": hb.state_since if hb.state_since is not None else existing.get("state_since"),
        "prev_state": hb.prev_state if hb.prev_state is not None else existing.get("prev_state"),
        "state_reason": hb.state_reason if hb.state_reason is not None else existing.get("state_reason"),
        "log_meta": hb.log_meta or existing.get("log_meta", {}),
        "cluster_integrity": hb.cluster_integrity or existing.get("cluster_integrity", {}),
        "streams": hb.streams or existing.get("streams", {}),
    }
    return {"ok": True}


@app.get("/dashboard/compact")
def dashboard_compact():
    """
    Dashboard compacto del cluster.

    Devuelve info completa de todos los nodos: state, ages, health, events counters,
    progress, integrity, etc. Para monitoring y debugging.
    """
    now = time.time()
    leader = compute_leader()
    local_events = events_summary()
    integrity = local_integrity_api()
    local_node = cluster_state.get(ctx.node_id, {}) or {}

    try:
        from cluster.runtime.progress_watchdog import (
            get_progress_age_s,
            get_progress_duration_s,
            get_progress_pct,
            refresh_progress_stalled_flag,
        )
    except Exception:
        get_progress_age_s = None
        get_progress_duration_s = None
        get_progress_pct = None
        refresh_progress_stalled_flag = None

    nodes = []
    for node_id, node in sorted(cluster_state.items(), key=lambda kv: str(kv[0])):
        log_meta = node.get("log_meta", {}) or {}
        counts = (((node.get("streams") or {}).get("events_summary_local") or {}).get("counts") or {})
        progress_age_s = None
        progress_duration_s = None
        progress_pct = None
        progress_stalled = bool(node.get("progress_stalled", False))

        if refresh_progress_stalled_flag is not None:
            try:
                progress_stalled = bool(refresh_progress_stalled_flag(node_id=node_id, now=now))
                node = cluster_state.get(node_id, node) or node
            except Exception:
                progress_stalled = bool(node.get("progress_stalled", False))

        if get_progress_age_s is not None:
            try:
                progress_age_s = get_progress_age_s(node=node, now=now)
            except Exception:
                progress_age_s = None

        if get_progress_duration_s is not None:
            try:
                progress_duration_s = get_progress_duration_s(node=node, now=now)
            except Exception:
                progress_duration_s = None

        if get_progress_pct is not None:
            try:
                progress_pct = get_progress_pct(node=node)
            except Exception:
                progress_pct = None
        else:
            try:
                current = node.get("progress_current")
                total = node.get("progress_total")
                if current is not None and total not in (None, 0):
                    progress_pct = round((float(current) / float(total)) * 100.0, 1)
            except Exception:
                progress_pct = None

        item = {
            "node_id": node_id,
            "state": node.get("state"),
            "state_since": node.get("state_since"),
            "state_age_s": round(_state_age_s(node, now) or 0.0, 1),
            "prev_state": node.get("prev_state"),
            "state_reason": node.get("state_reason"),
            "priority": node.get("priority"),
            "last_seen": node.get("last_seen"),
            "seen_age_s": round(_seen_age_s(node, now) or 0.0, 1),
            "last_watchdog": node.get("last_watchdog"),
            "watchdog_age_s": round(_watchdog_age_s(node, now) or 0.0, 1) if node.get("last_watchdog") is not None else None,
            "watchdog_busy": node.get("watchdog_busy"),
            "presence_age_s": round(_presence_age_s(node, now) or 0.0, 1),
            "health": _presence_health(node, now, stale_after_s=3.0),
            "local_size": log_meta.get("size", 0),
            "local_events": ((node.get("streams") or {}).get("events_summary_local") or {}).get("total_events", 0),
            "created": counts.get("created", 0),
            "executing": counts.get("executing", 0),
            "completed": counts.get("completed", 0),
            "dirty": ((node.get("cluster_integrity") or {}).get("last_append_meta") or {}).get("dirty"),
            "progress_active": bool(node.get("progress_active", False)),
            "progress_stage": node.get("progress_stage"),
            "progress_started_at": node.get("progress_started_at"),
            "progress_touched_at": node.get("progress_touched_at"),
            "progress_age_s": round(progress_age_s, 1) if progress_age_s is not None else None,
            "progress_duration_s": round(progress_duration_s, 1) if progress_duration_s is not None else None,
            "progress_current": node.get("progress_current"),
            "progress_total": node.get("progress_total"),
            "progress_pct": progress_pct,
            "progress_stalled": progress_stalled,
            "progress_meta": node.get("progress_meta") or {},
        }
        nodes.append(item)

    local_progress = {
        "progress_active": bool(local_node.get("progress_active", False)),
        "progress_stage": local_node.get("progress_stage"),
        "progress_started_at": local_node.get("progress_started_at"),
        "progress_touched_at": local_node.get("progress_touched_at"),
        "progress_age_s": None,
        "progress_duration_s": None,
        "progress_current": local_node.get("progress_current"),
        "progress_total": local_node.get("progress_total"),
        "progress_pct": None,
        "progress_stalled": bool(local_node.get("progress_stalled", False)),
        "progress_meta": local_node.get("progress_meta") or {},
    }

    return {
        "cluster": {
            "node_id": ctx.node_id,
            "leader": leader,
            "generated_at": now,
            "integrity_ok": bool(integrity.get("integrity_ok", True)),
            "local_state": ctx.node.state.value,
            "local_state_since": getattr(ctx.node, "state_since", None),
            "local_state_age_s": round(_state_age_s({"state_since": getattr(ctx.node, "state_since", None)}, now) or 0.0, 1),
        },
        "local": {
            "events_summary": local_events,
            "integrity": integrity,
            "progress": local_progress,
        },
        "nodes": nodes,
    }


@app.get("/integrity")
def integrity():
    """Devuelve el reporte de integridad local."""
    return local_integrity_api()


@app.get("/integrity/cluster")
def integrity_cluster():
    """Devuelve el reporte de integridad del cluster."""
    return cluster_integrity_report()
