# File: ./cluster/runtime/context.py
# Previous: none
# Author: alftorres
# Date: 2026-05-28T17:07:42+0200
# Version: 0.0.0
# Genealogy:
#   ./cluster/runtime/context.py 0.0.0 2026-05-28T17:07:42+0200
#   God
#
# Purpose:
#   Módulo de contexto global para el cluster.
#   Almacena variables de estado compartidas que se inicializan durante el bootstrap
#   y se acceden desde múltiples módulos sin pasarlas explícitamente como parámetros.
# Notes:
#   - Este patrón (global state) es común en sistemas single-threaded con event loop
#   - En un futuro considerar inyección de dependencias explícita para testabilidad
#   - Las variables se inicializan en None/empty y se llenan en bootstrap.py
#
# FRV-ID: fae1f65db3f7af4a
# Header_End

from typing import Any

# =============================================================================
# Variables globales de contexto del nodo
# =============================================================================

#: Objeto NodeRuntime completo del nodo actual (se inicializa en bootstrap)
#: Tipo: NodeRuntime | None
node = None

#: ID único del nodo actual dentro del cluster (string)
#: Se usa para identificar el nodo en heartbeats, leader election, etc.
#: Tipo: str | None
node_id = None

#: Alias de node_id para compatibilidad con código legacy
#: TODO: Deprecar y usar solo node_id
#: Tipo: str | None
nodeid = None

#: Lista de nodos peer en el cluster (lista de dicts con info de nodos)
#: Cada entry típicamente tiene: node_id, host, port, priority, state, etc.
#: Se actualiza en cluster_state durante bootstrap y heartbeats
#: Tipo: list[dict[str, Any]]
peers = []

#: Stream actual del nodo (para multiplexación de eventos por stream)
#: Si es None, se usa el stream por defecto o node_stream
#: Tipo: str | None
stream = None

#: Stream asociado al nodo (alternativa a stream)
#: Se prioriza stream sobre node_stream en get_stream()
#: Tipo: str | None
node_stream = None


def get_stream():
    """
    Devuelve el stream activo del nodo.

    Prioridad:
        1. `stream` (si está definido)
        2. `node_stream` (fallback)
        3. None (si ninguno está definido)

    Returns:
        str | None: El stream activo o None si no hay ninguno configurado.

    Example:
        >>> stream = get_stream()
        >>> if stream:
        ...     process_events(stream)
    """
    return stream or node_stream
