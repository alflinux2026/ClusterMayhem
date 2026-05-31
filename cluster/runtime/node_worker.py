# File: ./cluster/runtime/node_worker.py
# Previous: none
# Author: alftorres
# Date: 2026-05-28T17:11:20+0200
# Version: 0.0.0
# Genealogy:
#   ./cluster/runtime/node_worker.py 0.0.0 2026-05-28T17:11:20+0200
#   God
#
# Purpose:
#   Worker en background que ejecuta el tick del nodo cada ~1s.
#   NodeWorker es un hilo daemon que ejecuta loop infinito llamando a tick()
#   según el estado actual del nodo. Cada tick ejecuta: heartbeat, watchdog,
#   replicación de logs, check de estado de eventos, y transiciones a DRAINING/SEGMENTATION
#   si es necesario.
# Notes:
#   - Se arranca en run_node() como hilo daemon (no bloquea uvicorn)
#   - interval=1.0s por defecto (se puede ajustar con env var)
#   - tick_*() se llama según el estado: BOOT, STANDBY, ACTIVE, SEGMENTATION, DRAINING, ISOLATED, OFFLINE
#   -EVENTSTATECHECKPERIODSEC=10s: check de estado de eventos cada 10s
#   - STATEDEBUGPERIODSEC=30s: log de debug de estado cada 30s
#   - MAX_SEGMENT_COUNT=2500:enter DRAINING si total_events > 2500
#   - _can_segment(): solo se puede segmentar si created=0, executing=0, dirty=False
#
# FRV-ID: 09d53436254fce74
# Header_End

import os
import time
import threading
from pathlib import Path

from cluster.runtime.leader import compute_leader

from cluster.runtime.state import NodeState, get_state_age_s
from cluster.runtime import context as ctx
from cluster.utils.log_print import log_state
from cluster.runtime.event_log import rebuild_event_state_index, load_events, load_completed_events, get_local_log_path
from cluster.runtime.events.event_state import EventStatus
from cluster.runtime.log_replication import replicate_eventlog, replicate_events
from cluster.runtime.watchdog import emit_watchdog_if_due
from cluster.runtime.cluster_store import cluster_state
from cluster.runtime.api_app import _summarize_events

# =============================================================================
# Configuración del worker (mediante env vars)
# =============================================================================

#: Frecuencia de check de estado de eventos en segundos (default: 10s)
EVENTSTATECHECKPERIODSEC = float(os.getenv("EVENTSTATECHECKPERIODSEC", 10))

#: Frecuencia de log de debug de estado en segundos (default: 30s)
STATEDEBUGPERIODSEC = float(os.getenv("STATEDEBUGPERIODSEC", 30))

#: Máximo número de eventos antes de entrar en DRAINING (default: 2500)
MAX_SEGMENT_COUNT = int(os.getenv("MAX_SEGMENT_COUNT", 2500))

#: Timestamp del último check de estado de eventos
lasteventstatecheckts = 0.0

#: Timestamp del último log de debug de estado
laststatedebugts = 0.0


def _node_cache(node):
    """
    Obtiene el cache del nodo de cluster_state.

    Args:
        node: NodeRuntime o dict del nodo.

    Returns:
        dict: Cache del nodo (streams, counters, etc.), o {} si no existe.
    """
    node_id = _node_id(node)
    if not node_id:
        return {}
    data = cluster_state.get(node_id, {}) or {}
    return data if isinstance(data, dict) else {}


def _node_id(node):
    """
    Extrae el node_id de un nodo (dict o NodeRuntime).

    Args:
        node: NodeRuntime o dict.

    Returns:
        str: node_id del nodo, o "?" si no se puede extraer.
    """
    if isinstance(node, dict):
        return node.get("node_id", "?")
    return getattr(node, "node_id", "?")


def rebuild_node_event_cache(node_id: str):
    """
    Reconstruye el cache de eventos de un nodo en cluster_state.

    Carga eventos locales y completados, cuenta por status, y actualiza
    streams con resúmenes (events_summary_local, events_summary_created, etc.).

    Args:
        node_id: ID del nodo.

    Note:
        - Se llama en cada tick para actualizar counters
        - Actualiza cluster_state para que el dashboard muestre counters actualizados
    """
    if not isinstance(node_id, str):
        node_id = getattr(node_id, "node_id", None)

    if not node_id:
        log_state("red", "CACHE_BOOTSTRAP", "invalid node_id for event cache bootstrap", 3)
        return

    node = cluster_state.get(node_id, {}) or {}
    if not isinstance(node, dict):
        node = {}

    streams = dict(node.get("streams", {}) or {})

    local_events = load_events() or []
    completed_events = []
    try:
        completed_events = load_completed_events() or []
    except Exception as e:
        log_state("red", "CACHE_BOOTSTRAP", f"{node_id} completed_load_failed={e}", 3)

    created_events = [e for e in local_events if e.get("status") == EventStatus.CREATED.value]
    executing_events = [e for e in local_events if e.get("status") == EventStatus.EXECUTING.value]

    streams["events_summary_local"] = _summarize_events(local_events)
    streams["events_summary_created"] = _summarize_events(created_events)
    streams["events_summary_executing"] = _summarize_events(executing_events)
    streams["events_summary_completed"] = _summarize_events(completed_events)

    node["node_id"] = node_id
    node["streams"] = streams
    cluster_state[node_id] = node

    log_state("blue", "NODE STATE a", f"{_node_id(node)} local={len(local_events)} created={len(created_events)} executing={len(executing_events)} completed={len(completed_events)}", 3)


def _node_streams(node):
    """Obtiene streams del nodo (dict o NodeRuntime)."""
    if isinstance(node, dict):
        return node.get("streams", {}) or {}
    return getattr(node, "streams", {}) or {}


def _node_event_counters(node) -> tuple[int, int, int, int]:
    """
    Cuenta eventos por status del nodo.

    Returns:
        tuple[int, int, int, int]: (created, executing, completed, total)
    """
    cache = _node_cache(node)
    streams = cache.get("streams", {}) or {}
    summary = streams.get("events_summary_local", {}) or {}
    counts = summary.get("counts", {}) or {}
    created = int(counts.get("created", 0))
    executing = int(counts.get("executing", 0))
    completed = int(counts.get("completed", 0))
    total = int(summary.get("total_events", created + executing + completed))
    return created, executing, completed, total


def _can_segment(node) -> bool:
    """
    Comprueba si el nodo puede segmentar (rotar logs).

    Solo se puede segmentar si:
        - created > 0 (hay eventos sin procesar)
        - executing == 0 (no hay eventos en ejecución)
        - dirty == False (no hay replicación pendiente)

    Args:
        node: NodeRuntime del nodo.

    Returns:
        bool: True si se puede segmentar.
    """
    created, executing, completed, total = _node_event_counters(node)
    cache = _node_cache(node)
    dirty = bool(cache.get("dirty", False))
    return created > 0 and executing == 0 and not dirty


def _should_enter_DRAINING(node) -> bool:
    """
    Comprueba si el nodo debe entrar en DRAINING.

    Entra en DRAINING si total_events > MAX_SEGMENT_COUNT.

    Args:
        node: NodeRuntime del nodo.

    Returns:
        bool: True si debe entrar en DRAINING.
    """
    created, executing, completed, total = _node_event_counters(node)
    return total > MAX_SEGMENT_COUNT


def _should_enter_segmentation(node) -> bool:
    """
    Comprueba si el nodo debe entrar en SEGMENTATION.

    Entra en SEGMENTATION si _can_segment() es True.

    Args:
        node: NodeRuntime del nodo.

    Returns:
        bool: True si debe entrar en SEGMENTATION.
    """
    return _can_segment(node)


def leader_event_state_check_tick():
    """
    Check periódico del estado de eventos (cada EVENTSTATECHECKPERIODSEC).

    Carga eventos raw y del state_index, cuenta por status, y logea
    diferencias (si hay).

    Note:
        - Throttleado a EVENTSTATECHECKPERIODSEC=10s
        - Actualmente no hace nada con los conteos (solo cuenta)
    """
    global lasteventstatecheckts
    now = time.time()
    if now - lasteventstatecheckts < EVENTSTATECHECKPERIODSEC:
        return
    lasteventstatecheckts = now

    raw_events = load_events() or []
    state_index = rebuild_event_state_index()

    raw_created = raw_executing = raw_completed = 0
    for e in raw_events:
        status = e.get("status")
        if hasattr(status, "value"):
            status = status.value
        status = str(status).strip().lower()
        if status == EventStatus.CREATED.value:
            raw_created += 1
        elif status == EventStatus.EXECUTING.value:
            raw_executing += 1
        elif status == EventStatus.COMPLETED.value:
            raw_completed += 1

    created = executing = completed = 0
    for event in state_index.values():
        status = event.get("status") if isinstance(event, dict) else getattr(event, "status", None)
        if hasattr(status, "value"):
            status = status.value
        status = str(status).strip().lower()
        if status == EventStatus.CREATED.value:
            created += 1
        elif status == EventStatus.EXECUTING.value:
            executing += 1
        elif status == EventStatus.COMPLETED.value:
            completed += 1


def cleanup_local_segment_files(node_id: str, segment: str = "000", files=None):
    """
    Elimina archivos de segmento local después de rotar.

    Args:
        node_id: ID del nodo.
        segment: Segmento a limpiar (default: "000").
        files: Lista de tipos de archivos (default: ["events", "event_log"]).

    Returns:
        dict: Resumen de archivos eliminados y faltantes.
    """
    files = files or ["events", "event_log"]
    base_dir = Path(get_local_log_path(None)).resolve().parent
    removed = []
    missing = []

    for kind in files:
        p = base_dir / f"{kind}.local.{segment}.jsonl"
        if p.exists():
            p.unlink()
            removed.append(str(p))
        else:
            missing.append(str(p))

    return {
        "node_id": node_id,
        "segment": segment,
        "removed": removed,
        "missing": missing,
    }


def log_state_runtime_debug(node):
    """
    Log de debug de estado del nodo (cada STATEDEBUGPERIODSEC).

    Args:
        node: NodeRuntime del nodo.

    Note:
        - Throttleado a STATEDEBUGPERIODSEC=30s
        - Reconstruye cache de eventos antes de logear
    """
    global laststatedebugts
    now = time.time()
    if now - laststatedebugts < STATEDEBUGPERIODSEC:
        return
    laststatedebugts = now

    age_s = get_state_age_s(node, now=now)
    rebuild_node_event_cache(node.node_id)

    log_state("blue", "NODE STATE b", f"{_node_id(node)} state={node.state.value} age={age_s:.1f}s prev={getattr(node, 'prev_state', None)} reason={getattr(node, 'state_reason', None)}", 3)


def rotate_segment_files(target_group: str, segment: str = "000", files=None, force: bool = False):
    """
    Rota archivos de segmento (renombra .local.000.jsonl a .{node_id}.001.jsonl).

    Args:
        target_group: Grupo destino (no usado, se usa node_id local).
        segment: Segmento a rotar (default: "000").
        files: Lista de tipos de archivos (default: ["events", "event_log"]).
        force: Si True, crea entry incluso si el archivo no existe.

    Returns:
        dict: Resultado con before/after paths e índices.

    Raises:
        RuntimeError: Si no hay node_id local.
        FileNotFoundError: Si el archivo no existe y force=False.
    """
    files = files or ["events", "event_log"]
    base_dir = Path(get_local_log_path(None)).resolve().parent
    local_node_id = getattr(ctx, "node_id", None) or getattr(getattr(ctx, "node", None), "node_id", None)

    if not local_node_id:
        raise RuntimeError("missing local node_id for segment rotation")

    result = {}

    for kind in files:
        src = base_dir / f"{kind}.local.{segment}.jsonl"
        if not src.exists():
            if force:
                result[kind] = {"before": str(src), "after": None, "index": None, "forced": True}
                continue
            raise FileNotFoundError(str(src))

        idx = _next_rotation_index(base_dir, f"{kind}.{local_node_id}")
        dst = base_dir / f"{kind}.{local_node_id}.{idx:03d}.jsonl"
        os.replace(str(src), str(dst))
        result[kind] = {"before": str(src), "after": str(dst), "index": idx, "forced": False}

    return result


def _next_rotation_index(base_dir, stem, suffix=".jsonl"):
    """
    Encuentra el próximo índice disponible para rotación.

    Args:
        base_dir: Directorio base.
        stem: Prefix del archivo (ej: "event_log.lnx203hp").
        suffix: Suffix del archivo (default: ".jsonl").

    Returns:
        int: Próximo índice disponible (001, 002, ...).
    """
    base_dir = Path(base_dir)
    idx = 1
    while True:
        candidate = base_dir / f"{stem}.{idx:03d}{suffix}"
        if not candidate.exists():
            return idx
        idx += 1


class NodeWorker:
    """
    Worker en background que ejecuta el tick del nodo cada ~1s.

    Attributes:
        node (NodeRuntime): Nodo del cluster.
        peers (list[dict]): Lista de peers con host, port, node_id.
        interval (float): Intervalo entre ticks en segundos (default: 1.0).
        running (bool): Flag para controlar el loop.

    Example:
        >>> worker = NodeWorker(node, peers, interval=1.0)
        >>> worker.start()
        # Worker empieza a ejecutar tick cada 1s en hilo background
        >>> worker.stop()
        # Worker para el loop
    """

    def __init__(self, node, peers, interval=1.0):
        """
        Inicializa el worker.

        Args:
            node: NodeRuntime del nodo.
            peers: Lista de peers.
            interval: Intervalo entre ticks en segundos.
        """
        self.node = node
        self.peers = peers
        self.interval = interval
        self.running = False

    def start(self):
        """
        Arranca el worker en un hilo daemon.

        El hilo ejecuta loop() hasta que running=False.
        """
        self.running = True
        t = threading.Thread(target=self.loop, daemon=True)
        t.start()

    def stop(self):
        """Detiene el worker (setting running=False)."""
        self.running = False

    def tick_boot(self):
        """
        Tick del estado BOOT.

        - Emite watchdog busy=True
        - Reconstruye cache de eventos
        - Transiciona a STANDBY
        """
        emit_watchdog_if_due(self.peers, busy=True)
        rebuild_node_event_cache(self.node.node_id)
        self.node.event_cache_ready = True
        self.node.transition(NodeState.STANDBY, reason="boot_complete")

    def tick_discovering(self):
        """Tick del estado DISCOVERING (actualmente no hace nada)."""
        pass

    def tick_standby(self):
        """
        Tick del estado STANDBY.

        - Emite heartbeat a peers
        - Emite watchdog busy=True
        - Replica event log y events
        - Check de estado de eventos
        - Si total_events > MAX_SEGMENT_COUNT, transiciona a DRAINING
        """
        self.node.emit_heartbeat(self.peers)
        emit_watchdog_if_due(self.peers, busy=True)

        leader = compute_leader()

        replicate_eventlog()
        replicate_events()
        leader_event_state_check_tick()
        if _should_enter_DRAINING(self.node):
            self.node.transition(NodeState.DRAINING, reason="segment_max_count")

    def tick_active(self):
        """
        Tick del estado ACTIVE (líder).

        Igual que tick_standby() pero el nodo es el líder.
        """
        self.node.emit_heartbeat(self.peers)
        emit_watchdog_if_due(self.peers, busy=True)
        replicate_eventlog()
        replicate_events()
        leader_event_state_check_tick()
        if _should_enter_DRAINING(self.node):
            self.node.transition(NodeState.DRAINING, reason="segment_max_count")

    def tick_segmentation(self):
        """
        Tick del estado SEGMENTATION.

        - Si no se puede segmentar, retorna sin hacer nada
        - Rota archivos de segmento (.local.000.jsonl -> .{node_id}.001.jsonl)
        - Elimina archivos rotados
        - Reconstruye cache de eventos
        - Transiciona a STANDBY
        """
        self.node.emit_heartbeat(self.peers)
        emit_watchdog_if_due(self.peers, busy=True)

        can_seg = _can_segment(self.node)
        should_seg = _should_enter_segmentation(self.node)

        if not should_seg:
            return False

        result = rotate_segment_files(self.node.node_id, segment="000", files=["events", "event_log"], force=False)
        log_state("magenta", "SEGMENTATION", f"{self.node.node_id} rotate ok={bool(result)}", 3)

        cleanup_local_segment_files(self.node.node_id, segment="000", files=["events", "event_log"])
        rebuild_node_event_cache(self.node.node_id)
        self.node.transition(NodeState.STANDBY, reason="segment_closed")

        return True

    def tick_DRAINING(self):
        """
        Tick del estado DRAINING (preparando segmentación).

        - Emite heartbeat y watchdog
        - Replica logs
        - Reconstruye cache de eventos
        - Check de estado de eventos
        - Si _should_enter_segmentation(), transiciona a SEGMENTATION
        """
        self.node.emit_heartbeat(self.peers)
        emit_watchdog_if_due(self.peers, busy=True)
        replicate_eventlog()
        replicate_events()
        rebuild_node_event_cache(self.node.node_id)
        leader_event_state_check_tick()
        if _should_enter_segmentation(self.node):
            self.node.transition(NodeState.SEGMENTATION, reason="segment_ready")

    def tick_isolated(self):
        """Tick del estado ISOLATED (sleep/pausa, no hace nada)."""
        pass

    def tick_offline(self):
        """Tick del estado OFFLINE (desconectado, no hace nada)."""
        pass

    def _tick_by_state(self):
        """
        Despacha el tick según el estado actual del nodo.

        Llama a tick_boot(), tick_standby(), tick_active(), etc. según node.state.
        """
        state = self.node.state
        if state == NodeState.BOOT:
            self.tick_boot()
        elif state == NodeState.DISCOVERING:
            self.tick_discovering()
        elif state == NodeState.STANDBY:
            self.tick_standby()
        elif state == NodeState.ACTIVE:
            self.tick_active()
        elif state == NodeState.SEGMENTATION:
            self.tick_segmentation()
        elif state == NodeState.DRAINING:
            self.tick_DRAINING()
        elif state == NodeState.ISOLATED:
            self.tick_isolated()
        elif state == NodeState.OFFLINE:
            self.tick_offline()

    def loop(self):
        """
        Loop infinito del worker.

        Ejecuta:
            1. node.tick() (actualiza estado según quién es el líder)
            2. log_state_runtime_debug() (log cada 30s)
            3. Si estado es ISOLATED, skip el resto y sleep
            4. _tick_by_state() (tick según estado)
            5. Sleep hasta el próximo intervalo
        """
        while self.running:
            self.node.tick()
            log_state_runtime_debug(self.node)
            if self.node.state == NodeState.ISOLATED:
                continue
            self._tick_by_state()
            time.sleep(self.interval)
