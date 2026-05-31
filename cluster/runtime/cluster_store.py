# File: ./cluster/runtime/cluster_store.py
# Previous: none
# Author: alftorres
# Date: 2026-05-28T17:07:24+0200
# Version: 0.0.0
# Genealogy:
#   ./cluster/runtime/cluster_store.py 0.0.0 2026-05-28T17:07:24+0200
#   God
#
# Purpose:
#   Almacenamiento en memoria del estado del cluster.
#   Mantiene un diccionario global con el estado de todos los nodos del cluster,
#   actualizado mediante heartbeats. Se usa para leader election, watchdog,
#   y para consultar el estado de otros nodos.
# Notes:
#   - Este es un estado en memoria (no persiste, se reinicia al arrancar)
#   - Se llena con heartbeats de los nodos (ver heartbeat() en api_app.py)
#   - cluster_state vs CLUSTER_REGISTRY:
#       * CLUSTER_REGISTRY: nodos configurados estáticamente (host, port, priority)
#       * cluster_state: estado dinámico de nodos activos (state, last_seen, etc.)
#   - En un futuro podría amplificarse con persistencia o replicación
#
# FRV-ID: ed651d710eb25af1
# Header_End

import time

# =============================================================================
# Estado global del cluster (en memoria)
# =============================================================================

#: Diccionario global con el estado de todos los nodos del cluster
#: Clave: node_id (str)
#: Valor: dict con state, priority, last_seen, last_watchdog, watchdog_busy,
#:        state_since, prev_state, state_reason, log_meta, cluster_integrity, streams
#: Tipo: dict[str, dict[str, Any]]
cluster_state = {}


def get_active_cluster():
    """
    Devuelve el estado completo del cluster.

    Returns:
        dict[str, dict]: Copia de referencia de cluster_state con todos los nodos.

    Note:
        - Retorna la referencia directa (no una copia), así que cuidado con modificarlo
        - Se usa principalmente para debugging/monitoring

    Example:
        >>> cluster = get_active_cluster()
        >>> for node_id, info in cluster.items():
        ...     print(f"{node_id}: {info.get('state')}")
    """
    return cluster_state


def upsert_node(node_id: str, payload: dict, now: float | None = None) -> dict:
    """
    Inserta o actualiza un nodo en el cluster_state.

    Fusiona el payload con el estado existente del nodo, actualizando
    automáticamente `last_seen` al timestamp actual.

    Args:
        node_id: ID único del nodo.
        payload: Dict con los campos a actualizar (state, priority, last_watchdog, etc.).
        now: Timestamp opcional. Si no se proporciona, usa time.time().

    Returns:
        dict: El estado actualizado del nodo (después de la actualización).

    Example:
        >>> upsert_node("lnx203hp", {"state": "ACTIVE", "priority": 10})
        {'state': 'ACTIVE', 'priority': 10, 'last_seen': 1779956226.123}

    Note:
        - fusiona payload con el estado existente (no lo sobrescribe completamente)
        - last_seen siempre se actualiza al timestamp actual (a menos que payload lo fije)
    """
    now = now or time.time()
    current = cluster_state.get(node_id, {})

    cluster_state[node_id] = {
        **current,
        **payload,
        "last_seen": payload.get("last_seen", now),
    }
    return cluster_state[node_id]


def refresh_node_seen(node_id: str, now: float | None = None) -> dict:
    """
    Actualiza solo el last_seen de un nodo (heartbeat).

    Útil para refreshar el timestamp de actividad sin cambiar otros campos.

    Args:
        node_id: ID del nodo a refreshar.
        now: Timestamp opcional. Si no se proporciona, usa time.time().

    Returns:
        dict: El estado del nodo con last_seen actualizado.

    Example:
        >>> refresh_node_seen("lnx203hp")
        {'state': 'ACTIVE', 'priority': 10, 'last_seen': 1779956226.456}

    Note:
        - Solo actualiza last_seen, no cambia state/priority/otros campos
        - Se usa en heartbeats para marcar que el nodo sigue vivo
        - Si el nodo no existe, se crea con solo last_seen
    """
    now = now or time.time()
    current = cluster_state.get(node_id, {})

    cluster_state[node_id] = {
        **current,
        "last_seen": now,
    }
    return cluster_state[node_id]


def get_node(node_id: str) -> dict:
    """
    Obtiene el estado de un nodo del cluster.

    Args:
        node_id: ID del nodo a consultar.

    Returns:
        dict: El estado del nodo si existe, dict vacío {} si no existe.

    Example:
        >>> get_node("lnx203hp")
        {'state': 'ACTIVE', 'priority': 10, 'last_seen': 1779956226.123}

        >>> get_node("nodonotexist")
        {}

    Note:
        - Retorna dict vacío en lugar de None para evitar checks de None
        - Se usa en compute_leader(), compute_alive(), dashboard_compact(), etc.
    """
    return cluster_state.get(node_id, {})
