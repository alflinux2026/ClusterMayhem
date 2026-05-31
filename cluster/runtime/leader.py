# File: ./cluster/runtime/leader.py
# Previous: none
# Author: alftorres
# Date: 2026-05-28T17:10:07+0200
# Version: 0.0.0
# Genealogy:
#   ./cluster/runtime/leader.py 0.0.0 2026-05-28T17:10:07+0200
#   God
#
# Purpose:
#   Leader election para el cluster.
#   Implementa un algoritmo simple de leader election basado en priority:
#   el nodo con menor priority (y node_id alfabético como tie-breaker) se convierte
#   en líder. Los nodos deben estar "vivos" (heartbeat reciente) para ser considerados.
#   El líder es el único que procesa eventos; los nodos standby reenvían eventos al líder.
# Notes:
#   - Algoritmo: menor priority gana, tie-breaker es node_id alfabético
#   - Timeout por defecto: 1.5s (si no hay heartbeat en 1.5s, nodo se considera muerto)
#   - Solo nodos ACTIVE, STANDBY, STAND-BY, DRAINING son candidatos
#   - Se ejecuta en cada tick del worker (cada ~1s), así que la election es rápida
#   - No hay split-brain protection (asume red confiable)
#   - debug_node_id permite forzar un líder para testing
#
# FRV-ID: bc64b1dd697351a2
# Header_End

import time

from cluster.runtime.cluster_store import cluster_state
from cluster.runtime import context as ctx

# =============================================================================
# Configuración de leader election
# =============================================================================

#: Timeout en segundos para considerar un nodo como vivo
#: Si no hay heartbeat en este tiempo, el nodo se excluye de election
#: Tipo: float
LEADER_ALIVE_TIMEOUT = 1.5


def refresh_self_alive_entry(now=None):
    """
    Actualiza la entrada del nodo actual en cluster_state.

    Sincroniza el estado del nodo local (state, priority, last_seen) con
    cluster_state para que sea visible para la leader election.

    Args:
        now: Timestamp opcional. Si no se proporciona, usa time.time().

    Note:
        - Se llama en compute_alive() antes de election para asegurarse
          de que el nodo local está visible
        - Copia state, priority, last_seen, state_since, prev_state, state_reason
        - Si no hay ctx.node, retorna sin hacer nada


Example:
        >>> refresh_self_alive_entry()
        # cluster_state["lnx203hp"] = {..., "state": "ACTIVE", "priority": 10, "last_seen": 1779956226}
    """
    now = now or time.time()
    if not getattr(ctx, "node", None):
        return

    existing = cluster_state.get(ctx.node_id, {})

    cluster_state[ctx.node_id] = {
        **existing,
        "state": ctx.node.state.value,
        "priority": ctx.node.priority,
        "last_seen": now,
        "state_since": getattr(ctx.node, "state_since", None),
        "prev_state": getattr(ctx.node, "prev_state", None),
        "state_reason": getattr(ctx.node, "state_reason", None),
    }


def last_presence_ts(data: dict) -> float:
    """
    Obtiene el último timestamp de presencia de un nodo.

    Busca el máximo entre last_seen y last_watchdog para determinar
    cuándo fue la última vez que el nodo mostró actividad.

    Args:
        data: Dict con info del nodo (debe tener last_seen y/o last_watchdog).

    Returns:
        float: Último timestamp de presencia, o 0.0 si no hay ninguno.

    Example:
        >>> last_presence_ts({"last_seen": 1779956226.0, "last_watchdog": 1779956220.0})
        1779956226.0

        >>> last_presence_ts({"last_seen": None})
        0.0

    Note:
        - Ignora valores None o que no se puedan convertir a float
        - Se usa en is_alive() para determinar si el nodo está vivo
    """
    candidates = []
    for key in ("last_seen", "last_watchdog"):
        value = data.get(key, 0)
        if value is None:
            continue
        try:
            candidates.append(float(value))
        except Exception:
            continue
    return max(candidates) if candidates else 0.0


def is_alive(data, timeout=LEADER_ALIVE_TIMEOUT, now=None):
    """
    Comprueba si un nodo está vivo (heartbeat reciente).

    Args:
        data: Dict con info del nodo (last_seen o last_watchdog).
        timeout: Timeout en segundos para considerar vivo al nodo.
        now: Timestamp opcional. Si no se proporciona, usa time.time().

    Returns:
        bool: True si el nodo ha tenido actividad en los últimos `timeout` segundos.

    Example:
        >>> is_alive({"last_seen": 1779956226.0}, timeout=1.5, now=1779956227.0)
        True

        >>> is_alive({"last_seen": 1779956220.0}, timeout=1.5, now=1779956227.0)
        False

    Note:
        - Usa last_presence_ts() para obtener el último timestamp
        - Retorna True si (now - last_presence) < timeout
    """
    now = now or time.time()
    last_presence = last_presence_ts(data)
    return (now - last_presence) < timeout


def compute_alive(timeout=LEADER_ALIVE_TIMEOUT, include_self=True):
    """
    Calcula qué nodos están vivos y activos en el cluster.

    Filtra cluster_state para devolver solo nodos que:
        1. Son "vivos" (heartbeat en los últimos `timeout` segundos)
        2. Están en estado ACTIVE, STANDBY, STAND-BY, o DRAINING

    Args:
        timeout: Timeout para considerar vivo al nodo.
        include_self: Si True, actualiza la entrada del nodo local antes de calcular.

    Returns:
        dict[str, dict]: Nodos vivos mapeados por node_id con su info completa.

    Example:
        >>> compute_alive(timeout=1.5)
        {
            "lnx203hp": {"state": "ACTIVE", "priority": 10, "last_seen": 1779956226.0, ...},
            "lnx200nas": {"state": "STANDBY", "priority": 100, "last_seen": 1779956225.5, ...}
        }

    Note:
        - Llama a refresh_self_alive_entry() si include_self=True para asegurarse
          de que el nodo local está visible
        - Excluye nodos en BOOT, DISCOVERING, SEGMENTATION, ISOLATED, OFFLINE
    """
    now = time.time()
    if include_self:
        refresh_self_alive_entry(now)

    active_nodes = {}
    for node_id, data in cluster_state.items():
        if not is_alive(data, timeout=timeout, now=now):
            continue
        if data.get("state") not in ("ACTIVE", "STANDBY", "STAND-BY", "DRAINING"):
            continue
        active_nodes[node_id] = data
    return active_nodes


def compute_leader(debug_node_id=None, timeout=LEADER_ALIVE_TIMEOUT):
    """
    Calcula cuál es el líder del cluster.

    El líder es el nodo vivo con menor priority (tie-breaker: node_id alfabético).

    Args:
        debug_node_id: (Testing) Fuerza este node_id como líder.
        timeout: Timeout para considerar vivo al nodo.

    Returns:
        str | None: node_id del líder, o None si no hay nodos vivos.

    Example:
        >>> compute_leader()
        'lnx203hp'

        >>> compute_leader()  # Si todos los nodos están muertos
        None

    Note:
        - Algoritmo: min(priority, node_id) en nodos vivos
        - priority menor = más prioritario (el que gana)
        - Tie-breaker: node_id alfabético (lexicográfico)
        - Se llama en cada tick del worker (~1s) para detectar cambios de líder
        - Si no hay líder (todos muertos), dispatch_tick() no procesa eventos
    """
    active_nodes = compute_alive(timeout=timeout, include_self=True)
    if not active_nodes:
        return None
    return min(
        active_nodes.items(),
        key=lambda x: (x[1].get("priority", 9999), x[0]),
    )[0]
