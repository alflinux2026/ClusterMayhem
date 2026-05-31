# File: ./cluster/runtime/event_log.py
# Previous: none
# Author: alftorres
# Date: 2026-05-28T17:08:01+0200
# Version: 0.0.0
# Genealogy:
#   ./cluster/runtime/event_log.py 0.0.0 2026-05-28T17:08:01+0200
#   God
#
# Purpose:
#   Almacenamiento y gestión del event log del cluster.
#   Guarda eventos en archivos JSONL (one event per line), proporciona funciones
#   para cargar, filtrar, y appendear eventos. Mantiene dos logs:
#     - event_log.local.000.jsonl: eventos activos (CREATED, EXECUTING)
#     - events.local.000.jsonl: eventos completados (COMPLETED)
#   También gestiona el estado (dirty flags, last_append metadata) y la
#   replicación de logs a peers.
# Notes:
#   - JSONL format: cada línea es un JSON independiente (fácil append y tail)
#   - Escritura atómica de state (tmp + rename) para evitar corrupción
#   - Dirty flag se pone al append, se limpia al replicar exitosamente
#   - _update_node_events_cache() actualiza counters en cluster_state para dashboard
#   - get_created_events() y get_completed_event_ids() filtran por status
#   - Se usa en dispatcher.py, ingest.py, reconciler.py, api_app.py
#
# FRV-ID: da709be2675a0a9a
# Header_End

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any

from cluster.runtime.events.cluster_event import ClusterEvent
from cluster.runtime.events.event_state import EventStatus
from cluster.utils.log_print import log_state
from cluster.runtime.cluster_store import cluster_state

# =============================================================================
# Rutas de archivos de event log
# =============================================================================

#: Directorio de datos del cluster (../data relativo al archivo)
DATA_DIR = Path(__file__).resolve().parents[1] / "data"

#: Ruta del log local de eventos (JSONL)
LOCAL_LOG_PATH = DATA_DIR / "event_log.local.000.jsonl"

#: Ruta del log de eventos completados (JSONL)
COMPLETED_LOG_PATH = DATA_DIR / "events.local.000.jsonl"

#: Ruta del archivo de estado (last append metadata, dirty flags)
STATE_PATH = DATA_DIR / "last_append.state.json"

#: Lock para escrituras concurrentes de state (thread-safe)
_STATE_LOCK = threading.Lock()


def _update_node_events_cache(event: ClusterEvent, status: str):
    """
    Actualiza el cache de counters de eventos en cluster_state.

    Actualiza events_summary_local con total_events y counts por status.

    Args:
        event: Evento recién appended.
        status: Status del evento (CREATED, EXECUTING, COMPLETED, FAILED).

    Note:
        - Se llama en append_event() después de escribir el log
        - Actualiza cluster_state para que el dashboard muestre counters actualizados
        - Usa source_node o target_node para identificar el nodo
    """
    node_id = getattr(event, "source_node", None) or getattr(event, "target_node", None)
    if not node_id:
        return

    node = cluster_state.get(node_id, {}) or {}
    streams = dict(node.get("streams", {}) or {})

    local_summary = streams.get("events_summary_local", {}) or {}
    local_summary["last_event_id"] = event.event_id
    local_summary["counts"] = dict(local_summary.get("counts", {}) or {})
    local_summary["total_events"] = int(local_summary.get("total_events", 0)) + 1
    local_summary["counts"][status] = int(local_summary["counts"].get(status, 0)) + 1

    streams["events_summary_local"] = local_summary
    node["streams"] = streams
    cluster_state[node_id] = node


def get_integrity_canonical() -> dict:
    """
    Devuelve la vista canonical del log para verificar integridad.

    Returns:
        dict: Vista canonical con log_size, file_size, last_append_event_id, last_append_created_at.

    Note:
        - Se usa en integrity.py para comparar views entre nodos
        - SHA256 de este dict es el integrity_hash
    """
    state = read_state()
    return {
        "log_size": os.path.getsize(LOCAL_LOG_PATH) if LOCAL_LOG_PATH.exists() else 0,
        "file_size": os.path.getsize(LOCAL_LOG_PATH) if LOCAL_LOG_PATH.exists() else 0,
        "last_append_event_id": state.get("last_append_event_id"),
        "last_append_created_at": state.get("last_append_created_at"),
    }


def ensure_dir():
    """Crea DATA_DIR si no existe (incluye directorios padres)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def ensure_initial_files():
    """
    Crea los archivos iniciales si no existen.

    Crea:
        - last_append.state.json: estado con dirty flags y metadata
        - event_log.local.000.jsonl: log local de eventos (vacío)
        - events.local.000.jsonl: log de eventos completados (vacío)

    Note:
        - Se llama en append_event() antes de escribir
        - El state inicial tiene dirty=True para forzar replicación inicial
    """
    ensure_dir()

    if not STATE_PATH.exists():
        write_state({
            "dirty": True,
            "events_dirty": True,
            "last_append_event_id": None,
            "last_append_created_at": None,
            "last_append_updated_at": None,
            "last_completed_event_id": None,
            "last_completed_created_at": None,
            "last_completed_updated_at": None,
        })

    if not LOCAL_LOG_PATH.exists():
        LOCAL_LOG_PATH.touch()

    if not COMPLETED_LOG_PATH.exists():
        COMPLETED_LOG_PATH.touch()


def get_local_log_path(stream: str | None = None) -> str:
    """Devuelve la ruta del log local."""
    return str(LOCAL_LOG_PATH)


def get_completed_log_path(stream: str | None = None) -> str:
    """Devuelve la ruta del log de eventos completados."""
    return str(COMPLETED_LOG_PATH)


def get_state_path() -> str:
    """Devuelve la ruta del archivo de estado."""
    return str(STATE_PATH)


def get_replica_log_path(node_id: str) -> str:
    """
    Devuelve la ruta para el log replica de un peer.

    Args:
        node_id: ID del peer.

    Returns:
        str: Ruta del archivo replica (ej: data/event_log.lnx200nas.000.jsonl).
    """
    return str(DATA_DIR / f"event_log.{node_id}.000.jsonl")


def get_replica_events_path(node_id: str) -> str:
    """
    Devuelve la ruta para el events replica de un peer.

    Args:
        node_id: ID del peer.

    Returns:
        str: Ruta del archivo replica de events.
    """
    return str(DATA_DIR / f"events.{node_id}.000.jsonl")


def list_replica_log_paths() -> List[str]:
    """
    Lista todas las rutas de logs locales en DATA_DIR.

    Returns:
        list[str]: Rutas de archivos *.local.000.jsonl.
    """
    if not DATA_DIR.exists():
        return []

    out: List[str] = []
    for name in sorted(os.listdir(DATA_DIR)):
        if not name.endswith(".local.000.jsonl"):
            continue
        out.append(str(DATA_DIR / name))
    return out


def load_events_from_path(path: str) -> List[dict]:
    """
    Carga eventos de un archivo JSONL.

    Args:
        path: Ruta del archivo JSONL.

    Returns:
        list[dict]: Lista de eventos (dicts). Ignora líneas inválidas.
    """
    if not os.path.exists(path):
        return []

    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _write_json_atomic(target_path: Path, payload: dict):
    """
    Escribe un dict como JSON de forma atómica (thread-safe).

    Usa tempfile.mkstemp + fsync + os.replace para escritura atómica.

    Args:
        target_path: Ruta del archivo destino.
        payload: Dict a escribir.

    Note:
        - Usa _STATE_LOCK para evitar escrituras concurrentes
        - tempfile.mkstemp en el mismo directorio para os.replace atómico
    """
    ensure_dir()
    with _STATE_LOCK:
        fd, tmp_name = tempfile.mkstemp(
            prefix=f"{target_path.name}.",
            suffix=".tmp",
            dir=str(target_path.parent),
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, str(target_path))
        except Exception:
            try:
                os.remove(tmp_name)
            except FileNotFoundError:
                pass
            raise


def write_text_atomic(path: str, content: str):
    """
    Escribe texto en un archivo de forma atómica.

    Args:
        path: Ruta del archivo destino.
        content: Contenido a escribir.
    """
    ensure_dir()
    target_path = Path(path)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f"{target_path.name}.",
        suffix=".tmp",
        dir=str(target_path.parent),
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, str(target_path))
    except Exception:
        try:
            os.remove(tmp_name)
        except FileNotFoundError:
            pass
        raise


def read_local_log_text() -> str:
    """Lee todo el contenido del log local."""
    if not LOCAL_LOG_PATH.exists():
        return ""
    return LOCAL_LOG_PATH.read_text(encoding="utf-8")


def read_completed_log_text() -> str:
    """Lee todo el contenido del log de eventos completados."""
    if not COMPLETED_LOG_PATH.exists():
        return ""
    return COMPLETED_LOG_PATH.read_text(encoding="utf-8")


def write_replica_log(node_id: str, content: str):
    """Escribe el log como replica para un peer."""
    ensure_dir()
    write_text_atomic(get_replica_log_path(node_id), content)


def write_replica_events(node_id: str, content: str):
    """Escribe los events como replica para un peer."""
    ensure_dir()
    write_text_atomic(get_replica_events_path(node_id), content)


def write_completed_log(content: str):
    """Escribe el log de eventos completados."""
    ensure_dir()
    write_text_atomic(str(COMPLETED_LOG_PATH), content)


def read_state() -> dict:
    """
    Lee el estado del archivo state.

    Returns:
        dict: Estado con dirty flags y metadata, o {} si no existe.
    """
    if not STATE_PATH.exists():
        return {}

    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def get_last_append_meta() -> dict:
    """Devuelve metadata del último append."""
    state = read_state()
    return state if isinstance(state, dict) else {}


def write_state(state: dict):
    """Escribe el estado de forma atómica."""
    _write_json_atomic(STATE_PATH, state)


def clear_eventlog_dirty_state():
    """Limpia el dirty flag del event log (replicación exitosa)."""
    state = read_state()
    state["dirty"] = False
    write_state(state)


def clear_events_dirty_state():
    """Limpia el dirty flag del events log (replicación exitosa)."""
    state = read_state()
    state["events_dirty"] = False
    write_state(state)


def load_events() -> List[dict]:
    """Carga eventos del log local."""
    return load_events_from_path(str(LOCAL_LOG_PATH))


def load_local_events() -> List[dict]:
    """Alias de load_events()."""
    return load_events_from_path(str(LOCAL_LOG_PATH))


def load_completed_events() -> List[dict]:
    """Carga eventos del log de completados."""
    return load_events_from_path(str(COMPLETED_LOG_PATH))


def load_replica_events(node_id: str) -> List[dict]:
    """Carga eventos de la replica de un peer."""
    return load_events_from_path(get_replica_log_path(node_id))


def load_all_replica_events() -> List[dict]:
    """Carga eventos de todas las replicas."""
    events: List[dict] = []
    for path in list_replica_log_paths():
        events.extend(load_events_from_path(path))
    return events


def load_cluster_events() -> List[dict]:
    """Alias de load_all_replica_events()."""
    return load_all_replica_events()


def _normalize_event(e: dict) -> dict:
    """
    Normaliza un evento asegurando campos defaults.

    Args:
        e: Dict de evento.

    Returns:
        dict: Evento normalizado con schema_version, received_at, attempt, route_hops, execution_key.
    """
    e = dict(e)
    e["schema_version"] = str(e.get("schema_version", "0.1"))
    e.setdefault("received_at", None)
    e.setdefault("attempt", 0)
    e.setdefault("route_hops", [])
    e.setdefault("execution_key", None)
    return e


def _latest_map(events: List[dict]) -> Dict[str, dict]:
    """
    Crea un mapa event_id -> último evento (por orden en el log).

    Args:
        events: Lista de eventos (puede tener duplicados por event_id).

    Returns:
        dict[str, dict]: Mapa de event_id -> último evento.
    """
    latest: Dict[str, dict] = {}
    for e in events:
        e = _normalize_event(e)
        latest[e["event_id"]] = e
    return latest


def rebuild_event_state_index() -> Dict[str, dict]:
    """
    Reconstruye el index de eventos por event_id (último versión).

    Returns:
        dict[str, dict]: Mapa event_id -> último evento.
    """
    return _latest_map(load_events())


def get_latest_event(event_id: str) -> Optional[dict]:
    """
    Obtiene el último evento con un event_id específico.

    Args:
        event_id: ID del evento a buscar.

    Returns:
        dict | None: Último evento con ese event_id, o None si no existe.
    """
    events = load_events()
    for e in reversed(events):
        if e["event_id"] == event_id:
            return _normalize_event(e)
    return None


def get_created_events():
    """
    Obtiene eventos en estado CREATED.

    Returns:
        list[ClusterEvent]: Eventos con status=CREATED.
    """
    latest = rebuild_event_state_index()
    domain_events = [ClusterEvent(**e) for e in latest.values()]
    return [e for e in domain_events if e.status == EventStatus.CREATED]


def get_completed_event_ids():
    """
    Obtiene IDs de eventos en estado COMPLETED.

    Returns:
        set[str]: event_ids de eventos COMPLETED.
    """
    latest = rebuild_event_state_index()
    domain_events = [ClusterEvent(**e) for e in latest.values()]
    return {e.event_id for e in domain_events if e.status == EventStatus.COMPLETED}


def append_event(event: ClusterEvent):
    """
    Añade un evento al log local.

    Secuencia:
        1. Asegura archivos iniciales (ensure_initial_files)
        2. Crea record con campos del evento
        3. Añade línea al log local (JSONL append)
        4. Actualiza state con dirty=True y metadata del append
        5. Si status=CREATED, también añade al completed log
        6. Actualiza cache de counters en cluster_state

    Args:
        event: Evento a appendear.

    Note:
        - El dirty flag se pone para indicar que hay que replicar
        - Se escribe manualmente con fsync para asegurar durabilidad
        - Si falla write_state, imprime error pero no levanta exception
    """
    ensure_initial_files()

    record = {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "schema_version": str(event.schema_version),
        "created_at": event.created_at,
        "updated_at": getattr(event, "updated_at", None),
        "received_at": getattr(event, "received_at", None),
        "trace_id": event.trace_id,
        "target_node": event.target_node,
        "source_node": getattr(event, "source_node", None),
        "route_hops": list(getattr(event, "route_hops", []) or []),
        "status": event.status.value if hasattr(event.status, "value") else event.status,
        "attempt": event.attempt,
        "execution_key": getattr(event, "execution_key", None),
        "payload": event.payload,
    }

    line = json.dumps(record) + "\n"
    with open(LOCAL_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())

    state = read_state()
    state["dirty"] = True
    state["last_append_event_id"] = event.event_id
    state["last_append_created_at"] = event.created_at
    state["last_append_updated_at"] = getattr(event, "updated_at", None)

    if record["status"] == EventStatus.CREATED.value:
        with open(COMPLETED_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())

        state["events_dirty"] = True
        state["last_completed_event_id"] = event.event_id
        state["last_completed_created_at"] = event.created_at
        state["last_completed_updated_at"] = getattr(event, "updated_at", None)

    try:
        write_state(state)
        _update_node_events_cache(event, record["status"])

    except Exception as e:
        print(f"[STATE WRITE FAIL] {event.event_id} -> {e}")


def replay_events(handler, stream: str | None = None):
    """
    Reproduce todos los eventos del log llamando a handler para cada uno.

    Args:
        handler: Función a llamar para cada evento (event -> None).
        stream: (Opcional) Stream a filtrar (no implementado aún).

    Example:
        >>> def handler(event):
        ...     print(f"Replaying {event.event_id}")
        >>> replay_events(handler)
    """
    events = load_events()
    for raw in events:
        event = ClusterEvent(**_normalize_event(raw))
        handler(event)


def ingest_event(event, node_id):
    """
    Ingerta un evento (marca como CREATED y lo appendea).

    Args:
        event: Evento a ingerir.
        node_id: ID del nodo que ingiere (líder).

    Returns:
        dict: Resultado con event_id, status="accepted", leader, trace_id.

    Note:
        - Se llama desde POST /event en api_app.py
        - Marca el evento como CREATED (si no lo está ya)
        - Marca received_at (si no lo tiene ya)
        - Logeia el evento con log_state
    """
    event.mark_status(EventStatus.CREATED)
    event.mark_received()
    append_event(event)

    msg = event.payload.get("msg", "<no-msg>")

    log_state("yellow", "(EVENT)", f"{msg:12} -> CREATED", 3)
    log_state("cyan", "[EVENT OK]", f"{msg:12}", 3)

    return {
        "event_id": event.event_id,
        "status": "accepted",
        "leader": node_id,
        "trace_id": event.trace_id
    }
