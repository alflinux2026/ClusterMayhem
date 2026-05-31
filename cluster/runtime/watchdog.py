# File: ./cluster/runtime/watchdog.py
# Previous: none
# Author: alftorres
# Date: 2026-05-28T17:12:10+0200
# Version: 0.0.0
# Genealogy:
#   ./cluster/runtime/watchdog.py 0.0.0 2026-05-28T17:12:10+0200
#   God
#
# Purpose:
#   Mecanismo de watchdog para detectar nodos bloqueados.
#   Envía señales periódicas (watchdog) a todos los peers indicando si el nodo
#   está ocupado (busy) o libre. Si un nodo no envía watchdog en WATCHDOG_TIMEOUTSEC,
#   se considera bloqueado y los otros nodos pueden tomar acción.
# Notes:
#   - Se ejecuta en cada tick del worker (~1s) vía emit_watchdog_if_due()
#   - Throttle automático: no más de un watchdog cada WATCHDOG_PERIODSEC (0.5s por defecto)
#   - busy=True cuando el nodo está procesando eventos, busy=False cuando está libre
#   - Si un nodo está busy > timeout, se considera stuck y puede ser ignorado en election
#   - WATCHDOG_DEBUG=(1|true|yes|on) habilita logs detallados
#
# FRV-ID: 4aa43744dbd78882
# Header_End


import os
import time
import logging
import requests

from cluster.runtime import context as ctx
from cluster.runtime.cluster_store import cluster_state
from cluster.utils.log_print import log_state

logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("requests").setLevel(logging.ERROR)

# =============================================================================
# Configuración de watchdog (mediante env vars)
# =============================================================================

#: Frecuencia mínima entre watchdogs en segundos (default: 0.5s)
#: Evita enviar watchdogs demasiado seguido
WATCHDOG_PERIODSEC = float(os.getenv("WATCHDOG_PERIODSEC", 0.5))

#: Timeout para considerar un nodo como stuck en segundos (default: 1.0s)
#: Si un nodo no envía watchdog en este tiempo, se considera bloqueado
WATCHDOG_TIMEOUTSEC = float(os.getenv("WATCHDOG_TIMEOUTSEC", 1.0))

#: Habilita logs detallados de watchdog (default: False)
#: Activar con WATCHDOG_DEBUG=1 o WATCHDOG_DEBUG=true
WATCHDOG_DEBUG = str(os.getenv("WATCHDOG_DEBUG", "0")).strip().lower() in ("1", "true", "yes", "on")

#: Sesión HTTP reutilizable para requests (connection pooling)
HTTP = requests.Session()

#: Timestamp del último watchdog emitido (para throttle)
_last_watchdog_emit_ts = 0.0


def _iter_targets(peers):
    """
    Itera sobre los peers,YIELD node_id y dict del nodo.

    Soporta tanto dict (node_id -> node) como list (lista de nodes).

    Args:
        peers: Dict o list con info de peers.

    Yields:
        tuple[str, dict]: (node_id, node_dict) para cada peer.

    Example:
        >>> peers = {"lnx203hp": {"host": "10.0.0.1", "port": 8000}}
        >>> list(_iter_targets(peers))
        [("lnx203hp", {"host": "10.0.0.1", "port": 8000})]

        >>> peers = [{"node_id": "lnx203hp", "host": "10.0.0.1", "port": 8000}]
        >>> list(_iter_targets(peers))
        [("lnx203hp", {"node_id": "lnx203hp", "host": "10.0.0.1", "port": 8000})]
    """
    if isinstance(peers, dict):
        for peer_id, node in peers.items():
            if isinstance(node, dict):
                yield peer_id, node
        return

    if isinstance(peers, list):
        for node in peers:
            if not isinstance(node, dict):
                continue
            peer_id = node.get("node_id") or node.get("name") or node.get("host")
            if peer_id:
                yield peer_id, node
        return


def _mark_local_watchdog(emitted_at: float, busy: bool):
    """
    Actualiza el watchdog del nodo local en cluster_state.

    Marca el nodo local como busy/free y actualiza last_watchdog y last_seen.

    Args:
        emitted_at: Timestamp cuando se emitió el watchdog.
        busy: True si el nodo está ocupado, False si está libre.

    Note:
        - Actualiza tanto cluster_state como ctx.node (si existe)
        - Se llama antes de enviar watchdogs a peers
    """
    node_id = getattr(ctx, "node_id", None)
    if not node_id:
        return

    current = cluster_state.get(node_id, {})
    cluster_state[node_id] = {
        **current,
        "last_watchdog": emitted_at,
        "last_seen": emitted_at,
        "watchdog_busy": bool(busy),
    }

    try:
        ctx.node.last_watchdog = emitted_at
        ctx.node.watchdog_busy = bool(busy)
    except Exception:
        pass


def emit_watchdog(peers, force=False, busy=True):
    """
    Emite un watchdog a todos los peers.

    Envía POST /watchdog a cada peer indicando si el nodo está busy.
    Tiene throttle automático para no enviar demasiado seguido.

    Args:
        peers: Lista o dict de peers con host y port.
        force: Si True, ignora el throttle y envía siempre.
        busy: True si el nodo está ocupado procesando, False si está libre.

    Returns:
        bool: True si se emitió el watchdog, False si se throttleó.

    Example:
        >>> peers = [{"host": "10.0.0.1", "port": 8000}]
        >>> emit_watchdog(peers, busy=True)
        True

        >>> emit_watchdog(peers, busy=False)  # 0.1s después del anterior
        False  # Throttleado (menos de WATCHDOG_PERIODSEC)

    Note:
        - Throttle: no más de un watchdog cada WATCHDOG_PERIODSEC (0.5s por defecto)
        - force=True ignora el throttle (útil para eventos críticos)
        - busy=True cuando se está procesando eventos, busy=False cuando está idle
        - Actualiza cluster_state local antes de enviar
        - Logea detalles si WATCHDOG_DEBUG=True
    """
    global _last_watchdog_emit_ts

    if not getattr(ctx, "node_id", None):
        return False

    now = time.time()
    if not force and (now - _last_watchdog_emit_ts) < WATCHDOG_PERIODSEC:
        return False

    emitted_at = now
    _mark_local_watchdog(emitted_at, busy)

    payload = {
        "node_id": ctx.node_id,
        "busy": bool(busy),
        "emitted_at": emitted_at,
    }

    sent = 0
    attempted = 0

    for peer_id, node in _iter_targets(peers):
        host = node.get("host")
        port = node.get("port")
        if not host or not port:
            continue

        attempted += 1
        url = f"http://{host}:{port}/watchdog"
        try:
            resp = requests.post(url, json=payload, timeout=WATCHDOG_TIMEOUTSEC)
            if resp.ok:
                sent += 1
            elif WATCHDOG_DEBUG:
                log_state("yellow", "WATCHDOG", f"peer={peer_id} status={resp.status_code}", 3)
        except Exception as e:
            if WATCHDOG_DEBUG:
                log_state("red", "WATCHDOG", f"peer={peer_id} err={e}", 3)

    _last_watchdog_emit_ts = emitted_at

    if WATCHDOG_DEBUG:
        log_state(
            "cyan",
            "WATCHDOG",
            f"node={ctx.node_id} sent={sent}/{attempted} busy={bool(busy)} ts={emitted_at:.3f}",
            3,
        )

    return True


def emit_watchdog_if_due(peers, busy=True):
    """
    Emite watchdog si ha pasado suficiente tiempo (throttle respetado).

    Wrapper de emit_watchdog() con force=False.

    Args:
        peers: Lista o dict de peers.
        busy: True si el nodo está ocupado, False si está libre.

    Returns:
        bool: True si se emitió, False si se throttleó.

    Example:
        >>> emit_watchdog_if_due(peers, busy=True)
        # Se llama en cada tick del worker (~1s)
    """
    return emit_watchdog(peers=peers, force=False, busy=busy)


def emit_watchdog_now(peers, busy=True):
    """
    Emite watchdog inmediatamente, ignorando el throttle.

    Wrapper de emit_watchdog() con force=True.

    Args:
        peers: Lista o dict de peers.
        busy: True si el nodo está ocupado, False si está libre.

    Returns:
        bool: Siempre True (si hay node_id).

    Example:
        >>> emit_watchdog_now(peers, busy=True)
        # Se envía inmediatamente, sin esperar WATCHDOG_PERIODSEC
    """
    return emit_watchdog(peers=peers, force=True, busy=busy)
