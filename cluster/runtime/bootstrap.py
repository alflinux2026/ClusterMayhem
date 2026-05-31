# File: ./cluster/runtime/bootstrap.py
# Previous: none
# Author: alftorres
# Date: 2026-05-28T17:06:16+0200
# Version: 0.0.0
# Genealogy:
#   ./cluster/runtime/bootstrap.py 0.0.0 2026-05-28T17:06:16+0200
#   God
#
# Purpose:
#   Bootstrap de configuración del nodo.
#   Carga la configuración del cluster desde un archivo nodes.json, identifica
#   cuál es el nodo local (por hostname, NODE_ID, NODE_HOST, o NODE_IP), Extrae
#   la configuración del nodo local y de los peers, y la guarda en config/node.json
#   para uso futuro. Si ya existe config/node.json con el mismo node_id, lo usa
#   (con merge de configuración).
# Notes:
#   - nodes.json define TODOS los nodos del cluster (lista completa)
#   - node.json es la configuración del NODO LOCAL (se genera automáticamente)
#   - Identificación del nodo local por prioridad: NODE_ID > NODE_HOST > NODE_IP > hostname
#   - Escritura atómica de node.json (tmp + rename) para evitar corrupción
#   - Environment vars override: NODE_ID, NODE_HOST, NODE_IP, NODE_PORT, etc.
#   - Si node.json existe y tiene el mismo node_id, se hace merge (no se sobrescribe todo)
#
# FRV-ID: 94320b527b1c5a2b
# Header_End

import json
import os
import socket
from pathlib import Path


def _write_json_atomic(path: str, data: dict) -> None:
    """
    Escribe un dict como JSON de forma atómica.

    Usa el patrón write-to-temp + rename para evitar corrupción si falla
    la escritura (power failure, crash, etc.).

    Args:
        path: Ruta del archivo destino.
        data: Dict a escribir como JSON.

    Note:
        - Crea el directorio padre si no existe
        - Escribe en archivo .tmp y luego hace os.replace()
        - flush() + fsync() aseguran que los datos llegan al disco
        - os.replace() es atómico en casi todos los filesystems

    Example:
        >>> _write_json_atomic("config/node.json", {"node_id": "lnx203hp"})
        # Crea config/ si no existe, escribe config/node.json.tmp, luego renombra
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def _node_get(node: dict, *keys, default=None):
    """
    Obtiene el primer valor no-None de un dict buscando varias claves.

    Útil para soportar nombres alternativos de claves (node_id vs nodeid, etc.).

    Args:
        node: Dict a buscar.
        *keys: Claves a buscar en orden.
        default: Valor por defecto si ninguna clave existe.

    Returns:
        El primer valor no-None encontrado, o default.

    Example:
        >>> node = {"hostname": "lnx203hp", "port": 8000}
        >>> _node_get(node, "node_id", "nodeid", "hostname")
        'lnx203hp'

        >>> _node_get(node, "port", "bind_port", default=7000)
        8000

        >>> _node_get(node, "missing", default="fallback")
        'fallback'
    """
    for key in keys:
        if key in node and node[key] is not None:
            return node[key]
    return default


def _find_self_node(nodes: list[dict]) -> dict:
    """
    Identifica cuál es el nodo local en la lista de nodos del cluster.

    Busca por prioridad:
        1. NODE_ID o NODEID env var coincide con node_id
        2. NODE_HOST o NODEHOST env var coincide con host
        3. NODE_IP o NODEIP env var coincide con host
        4. node_id coincide con hostname del sistema
        5. host coincide con hostname del sistema

    Args:
        nodes: Lista de dicts con info de nodos del cluster.

    Returns:
        dict: El dict del nodo local.

    Raises:
        RuntimeError: Si no se puede identificar el nodo local.

    Example:
        >>> nodes = [
        ...     {"node_id": "lnx203hp", "host": "10.0.0.1", "port": 8000},
        ...     {"node_id": "lnx200nas", "host": "10.0.0.2", "port": 8000}
        ... ]
        >>> _find_self_node(nodes)  # Si hostname es "lnx203hp"
        {"node_id": "lnx203hp", "host": "10.0.0.1", "port": 8000}

    Note:
        - La identificación es importante para saber qué nodo soy en el cluster
        - Soporta env vars para override en entornos container/Docker/K8s
    """
    hostname = socket.gethostname()

    node_id_env = os.getenv("NODE_ID") or os.getenv("NODEID")
    host_env = os.getenv("NODE_HOST") or os.getenv("NODEHOST")
    ip_env = os.getenv("NODE_IP") or os.getenv("NODEIP")

    for node in nodes:
        node_id = _node_get(node, "node_id", "nodeid")
        host = _node_get(node, "host", "hostname", "ip")

        if node_id_env and node_id == node_id_env:
            return node
        if host_env and host == host_env:
            return node
        if ip_env and host == ip_env:
            return node
        if node_id == hostname:
            return node
        if host == hostname:
            return node

    raise RuntimeError(
        f"Cannot identify node for hostname={hostname!r} "
        f"env NODE_ID={node_id_env!r} NODE_HOST={host_env!r} NODE_IP={ip_env!r}"
    )


def load_or_bootstrap_config():
    """
    Carga o genera la configuración del nodo.

    Secuencia:
        1. Carga nodes.json (lista completa de nodos del cluster)
        2. Identifica el nodo local (_find_self_node)
        3. Extrae configuración del nodo local y peers
        4. Si node.json existe y tiene el mismo node_id, hace merge y retorna
        5. Si no, genera node.json con la configuración y la retorna

    Returns:
        dict: Configuración del nodo con:
            - cluster_name (str): Nombre del cluster
            - node_id (str): ID único del nodo
            - priority (int): Prioridad para leader election
            - port (int): Puerto del nodo
            - host (str): Hostname/IP del nodo
            - bind_host (str): Host para bind del servidor
            - bind_port (int): Puerto para bind del servidor
            - tenants_id, app_id, data_type, schema_version (str): Metadatos
            - peers (list[dict]): Lista de peers con node_id, host, port, priority

    Raises:
        FileNotFoundError: Si nodes.json no existe.
        ValueError: Si nodes.json tiene formato inválido o está vacío.
        RuntimeError: Si no se puede identificar el nodo local.

    Example:
        >>> config = load_or_bootstrap_config()
        >>> config["node_id"]
        'lnx203hp'
        >>> config["peers"]
        [{'node_id': 'lnx200nas', 'host': '10.0.0.2', 'port': 8000, 'priority': 100}]

    Note:
        - nodes.json por defecto: cluster/config/nodes.json
        - node.json por defecto: config/node.json
        - Se puede override con env vars: CLUSTER_NODES, CLUSTER_CONFIG
        - Env vars adicionales: NODE_ID, NODE_HOST, NODE_IP, NODE_PORT, TENANT_ID, APP_ID, etc.
    """
    nodes_path = Path(os.getenv("CLUSTER_NODES", "cluster/config/nodes.json"))
    config_path = Path(os.getenv("CLUSTER_CONFIG", "config/node.json"))

    if not nodes_path.exists():
        raise FileNotFoundError(f"Missing cluster nodes file: {nodes_path}")

    with open(nodes_path, "r", encoding="utf-8") as f:
        cluster_cfg = json.load(f)

    if not isinstance(cluster_cfg, dict):
        raise ValueError(f"Invalid cluster nodes file: {nodes_path}")

    nodes = cluster_cfg.get("nodes", [])
    if not isinstance(nodes, list) or not nodes:
        raise ValueError(f"Empty node list in: {nodes_path}")

    self_node = _find_self_node(nodes)

    self_node_id = _node_get(self_node, "node_id", "nodeid")
    self_priority = int(_node_get(self_node, "priority", default=100))
    self_host = _node_get(self_node, "host", "hostname", "ip", default=os.getenv("NODE_HOST", "0.0.0.0"))
    self_port = int(_node_get(self_node, "port", default=os.getenv("NODE_PORT", "8000")))
    self_bind_host = _node_get(self_node, "bind_host", default=self_host)
    self_bind_port = int(_node_get(self_node, "bind_port", default=self_port))

    peers = []
    for n in nodes:
        peer_node_id = _node_get(n, "node_id", "nodeid")
        if peer_node_id == self_node_id:
            continue
        peers.append({
            "node_id": peer_node_id,
            "host": _node_get(n, "host", "hostname", "ip"),
            "port": int(_node_get(n, "port")),
            "priority": int(_node_get(n, "priority", default=100)),
        })

    cfg = {
        "cluster_name": cluster_cfg.get("cluster_name", "mayhem-cluster"),
        "node_id": self_node_id,
        "priority": self_priority,
        "port": self_port,
        "host": self_host,
        "bind_host": self_bind_host,
        "bind_port": self_bind_port,
        "tenant_id": os.getenv("TENANT_ID", "default"),
        "app_id": os.getenv("APP_ID", "mayhem"),
        "data_type": os.getenv("DATA_TYPE", "event"),
        "schema_version": os.getenv("SCHEMA_VERSION", "0.1"),
        "peers": peers,
    }

    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            if isinstance(existing, dict) and existing.get("node_id") == cfg["node_id"]:
                merged = {**existing, **cfg}
                merged["peers"] = cfg["peers"]
                return merged
        except (json.JSONDecodeError, OSError):
            pass

    _write_json_atomic(str(config_path), cfg)
    return cfg
