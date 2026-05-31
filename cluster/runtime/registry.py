# File: ./cluster/runtime/registry.py
# Previous: none
# Author: alftorres
# Date: 2026-05-28T17:11:35+0200
# Version: 0.0.0
# Genealogy:
#   ./cluster/runtime/registry.py 0.0.0 2026-05-28T17:11:35+0200
#   God
#
# Purpose:
#   Registro centralizado de nodos del cluster.
#   Mantiene un diccionario global con la información de todos los nodos
#   (host, port, priority) para permitir el enrutado de eventos y la
#   comunicación entre nodos.
# Notes:
#   - Este registro se inicializa durante el bootstrap con los nodos configurados
#   - Se usa en event_router.py para enrutar eventos al líder
#   - En un cluster dinámico, podría ampliarse con registro/descubrimiento automático
#   - No hay limpieza de nodos caídos (se asume estático o gestionado externamente)
#
# FRV-ID: 534531c72532d0c5
# Header_End

# =============================================================================
# Registro global de nodos del cluster
# =============================================================================

#: Diccionario global que mapea node_id -> información del nodo
#: Cada entry contiene: host, port, priority
#: Tipo: dict[str, dict[str, str | int]]
CLUSTER_REGISTRY = {}


def register_node(node_id: str, host: str, port: int, priority: int = 100):
    """
    Registra un nodo en el cluster.

    Añade o actualiza un nodo en el registry con su información de conexión.

    Args:
        node_id: ID único del nodo (string).
        host: Hostname o IP del nodo (ej: "100.100.1.200", "localhost").
        port: Puerto del nodo (ej: 8000, 7000).
        priority: Prioridad del nodo para leader election (menor = más prioridad).
                  Por defecto: 100.

    Returns:
        dict: El entry del nodo recién registrado/actualizado.

    Example:
        >>> register_node("lnx203hp", "100.100.1.200", 8000, priority=10)
        {'host': '100.100.1.200', 'port': 8000, 'priority': 10}

        >>> register_node("lnx200nas", "100.100.1.201", 8000)
        {'host': '100.100.1.201', 'port': 8000, 'priority': 100}

    Note:
        - Si el node_id ya existe, se sobrescribe la información
        - El priority se usa en compute_leader() para seleccionar el líder
    """
    CLUSTER_REGISTRY[node_id] = {
        "host": host,
        "port": port,
        "priority": priority,
    }
    return CLUSTER_REGISTRY[node_id]


def get_node(node_id: str):
    """
    Obtiene la información de un nodo del registry.

    Args:
        node_id: ID del nodo a buscar.

    Returns:
        dict | None: El dict del nodo si existe, None si no está registrado.

    Example:
        >>> get_node("lnx203hp")
        {'host': '100.100.1.200', 'port': 8000, 'priority': 10}

        >>> get_node("nodonotexist")
        None

    Note:
        - Se usa en event_router.py para obtener host/port del líder
        - Retorna None si el nodo no está en el registry (no levanta exception)
    """
    return CLUSTER_REGISTRY.get(node_id)
