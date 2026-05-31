# File: ./cluster/runtime/integrity.py
# Previous: none
# Author: alftorres
# Date: 2026-05-28T17:09:52+0200
# Version: 0.0.0
# Genealogy:
#   ./cluster/runtime/integrity.py 0.0.0 2026-05-28T17:09:52+0200
#   God
#
# Purpose:
#   Verificación de integridad del cluster.
#   Comprueba que todos los nodos tienen una vista consistente del cluster_state.
#   Каноникализирует los datos (ordena claves, ignora last_seen) y compara hash SHA256
#   para detectar divergencias. Se usa para debugging y para detectar split-brain.
# Notes:
#   - canonicalize() ordena claves recursivamente para comparar dicts independientemente del orden
#   - IGNORED_NODE_KEYS = {"last_seen"} se ignora porque cambia constantemente
#   - integrity_ok = True si todos los nodos tienen la misma vista
#   - Se llama desde /integrity y /integrity/cluster en api_app.py
#   - compute_views() compacta la vista para reducir ruido en logs
#
# FRV-ID: bb416140aa771527
# Header_End


import os
import hashlib
from typing import Any

from cluster.runtime import context as ctx
from cluster.runtime.cluster_store import cluster_state

import json
from cluster.runtime.event_log import get_integrity_canonical

from cluster.runtime.leader import compute_alive

# =============================================================================
# Configuración de integridad
# =============================================================================

#: Claves a ignorar al comparar views (cambian constantemente)
IGNORED_NODE_KEYS = {"last_seen"}

# descomentado si hace falta validar log_meta
#INTEGRITY_KEYS = (
#    "dirty",
#    "last_append_event_id",
#    "last_append_created_at",
#    "log_size",
#    "file_size",
#    "file_hash",
#)


#def file_sha256(path: str | Path, block_size: int = 65536) -> str | None:
#    """Calcula SHA256 de un archivo."""
#    path = str(path)
#    if not os.path.exists(path):
#        return None
#    h = hashlib.sha256()
#    with open(path, "rb") as f:
#        while True:
#            chunk = f.read(block_size)
#            if not chunk:
#                break
#            h.update(chunk)
#    return h.hexdigest()


def canonicalize(obj: Any, ignored_keys: set[str] | None = None) -> Any:
    """
    Canonicaiza un objeto recursivamente (ordena claves, ignora ciertas keys).

    Útil para comparar dicts independientemente del orden de las claves.

    Args:
        obj: Objeto a canonicalizar (dict, list, o escalar).
        ignored_keys: Conjunto de claves a ignorar (no incluir en el resultado).

    Returns:
        Any: Objeto canonicalizado (dict con claves ordenadas, list procesada, o escalar).

    Example:
        >>> canonicalize({"b": 2, "a": 1})
        {'a': 1, 'b': 2}

        >>> canonicalize({"b": 2, "a": 1}, ignored_keys={"a"})
        {'b': 2}

        >>> canonicalize([{"b": 2, "a": 1}])
        [{'a': 1, 'b': 2}]

    Note:
        - Se usa antes de comparar views para ignorar el orden de claves
        - Ignora recursivamente las claves en ignored_keys
    """
    ignored_keys = ignored_keys or set()
    if isinstance(obj, dict):
        return {
            k: canonicalize(v, ignored_keys)
            for k, v in sorted(obj.items())
            if k not in ignored_keys
        }
    if isinstance(obj, list):
        return [canonicalize(v, ignored_keys) for v in obj]
    return obj


def compare_views(a: dict, b: dict) -> bool:
    """
    Compara dos views canonicalizando primero.

    Args:
        a: Primer dict a comparar.
        b: Segundo dict a comparar.

    Returns:
        bool: True si las views son iguales después de canonicalizar.

    Example:
        >>> compare_views({"b": 2, "a": 1}, {"a": 1, "b": 2})
        True

        >>> compare_views({"b": 2, "a": 1}, {"a": 1, "b": 3})
        False
    """
    return canonicalize(a, IGNORED_NODE_KEYS) == canonicalize(b, IGNORED_NODE_KEYS)


#def log_meta_ok(local_meta: dict, peer_meta: dict) -> bool:
#    """Compara log_meta entre nodos."""
#    return all(local_meta.get(k) == peer_meta.get(k) for k in INTEGRITY_KEYS)


def _compact_view(view: dict) -> dict:
    """
    Compacta una view a solo los campos relevantes para debugging.

    Args:
        view: Dict completo de un nodo.

    Returns:
        dict: View compacta con state, state_since, prev_state, state_reason, priority, log_meta, streams.

    Example:
        >>> view = {"state": "ACTIVE", "state_since": 123, "extra": "ruido", "priority": 10}
        >>> _compact_view(view)
        {'state': 'ACTIVE', 'state_since': 123, 'prev_state': None, 'state_reason': None, 'priority': 10, 'log_meta': {}, 'streams': {}}
    """
    if not isinstance(view, dict):
        return {}
    return {
        "state": view.get("state"),
        "state_since": view.get("state_since"),
        "prev_state": view.get("prev_state"),
        "state_reason": view.get("state_reason"),
        "priority": view.get("priority"),
        "log_meta": view.get("log_meta", {}),
        "streams": view.get("streams", {}),
    }


def local_integrity_api() -> dict:
    """
    Verifica la integridad local del cluster.

    Compara la view del nodo local con la de todos los nodos vivos.

    Returns:
        dict: Resultado de la verificación:
            - node_id (str): ID del nodo local
            - alive_nodes (list[str]): Nodos vivos
            - self_view (dict): View compacta del nodo local
            - peer_status (dict[str, dict]): Status de cada peer
            - integrity_canonical (dict): View canonicalizada
            - integrity_hash (str): SHA256 de la view canonical
            - integrity_ok (bool): True si todos los peers tienen la misma view

    Example:
        >>> local_integrity_api()
        {
            'node_id': 'lnx203hp',
            'alive_nodes': ['lnx203hp', 'lnx200nas'],
            'self_view': {'state': 'ACTIVE', 'priority': 10, ...},
            'peer_status': {'lnx203hp': {'view_ok': True}, 'lnx200nas': {'view_ok': True}},
            'integrity_hash': 'abc123...',
            'integrity_ok': True
        }
    """
    alive = compute_alive(include_self=True)

    canonical = get_integrity_canonical()
    integrity_hash = hashlib.sha256(
        json.dumps(canonical, sort_keys=True).encode("utf-8")
    ).hexdigest()

    peer_status = {}
    self_view = canonicalize(cluster_state.get(ctx.node_id, {}), IGNORED_NODE_KEYS)
    self_meta = self_view.get("log_meta", {}) if isinstance(self_view, dict) else {}

    for node_id, data in alive.items():
        view = canonicalize(data, IGNORED_NODE_KEYS)
        meta = view.get("log_meta", {}) if isinstance(view, dict) else {}
        peer_status[node_id] = {
            "view": _compact_view(view),
            "view_ok": view == canonicalize(cluster_state.get(node_id, {}), IGNORED_NODE_KEYS),
        }

    return {
        "node_id": ctx.node_id,
        "alive_nodes": sorted(alive.keys()),
        "self_view": _compact_view(self_view),
        "peer_status": peer_status,
        "integrity_canonical": canonical,
        "integrity_hash": integrity_hash,
        "integrity_ok": all(v["view_ok"] for v in peer_status.values()),
    }


def cluster_integrity_report() -> dict:
    """
    Genera un reporte de integridad completo del cluster.

    Compara cada nodo con una referencia (cluster_state completo).

    Returns:
        dict: Reporte de integridad:
            - node_id (str): ID del nodo local
            - alive_nodes (list[str]): Nodos vivos
            - reference (dict[str, dict]): View canonicalizada de cada nodo
            - per_peer (dict[str, dict]): Detalle por peer
            - integrity_ok (bool): True si todos coinciden con la referencia

    Example:
        >>> cluster_integrity_report()
        {
            'node_id': 'lnx203hp',
            'alive_nodes': ['lnx203hp', 'lnx200nas'],
            'reference': {'lnx203hp': {...}, 'lnx200nas': {...}},
            'per_peer': {
                'lnx203hp': {'matches_reference': True, 'matches_log_meta': True, 'state': 'ACTIVE', ...},
                'lnx200nas': {'matches_reference': True, 'matches_log_meta': True, 'state': 'STANDBY', ...}
            },
            'integrity_ok': True
        }
    """
    alive = compute_alive(include_self=True)
    reference = canonicalize(cluster_state, IGNORED_NODE_KEYS)
    per_peer = {}

    for node_id, data in alive.items():
        view = canonicalize(data, IGNORED_NODE_KEYS)
        meta = view.get("log_meta", {}) if isinstance(view, dict) else {}
        ref_view = reference.get(node_id, {})
        ref_meta = ref_view.get("log_meta", {}) if isinstance(ref_view, dict) else {}

        per_peer[node_id] = {
            "matches_reference": view == ref_view,
            "matches_log_meta": meta == ref_meta,
            "state": view.get("state"),
            "state_since": view.get("state_since"),
            "prev_state": view.get("prev_state"),
            "state_reason": view.get("state_reason"),
            "priority": view.get("priority"),
            "streams": view.get("streams", {}),
        }

    return {
        "node_id": ctx.node_id,
        "alive_nodes": sorted(alive.keys()),
        "reference": {k: _compact_view(v) for k, v in reference.items()} if isinstance(reference, dict) else {},
        "per_peer": per_peer,
        "integrity_ok": all(v["matches_reference"] and v["matches_log_meta"] for v in per_peer.values()),
    }
