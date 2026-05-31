# File: ./cluster/runtime/log_replication.py
# Previous: none
# Author: alftorres
# Date: 2026-05-28T17:10:30+0200
# Version: 0.0.0
# Genealogy:
#   ./cluster/runtime/log_replication.py 0.0.0 2026-05-28T17:10:30+0200
#   God
#
# Purpose:
#   Replicación de logs del cluster entre nodos.
#   Replica el event log local a todos los peers vivos para mantener una copia
#   redundante de los eventos. Se ejecuta en cada tick del worker y solo replica
#   si el log está marcado como "dirty" (modificado). Cada peer recibe el log
#   y lo guarda como replica para poder recover en caso de fallo.
# Notes:
#   - Dos tipos de replicación: event log (eventos activos) y completed log (eventos procesados)
#   - Solo se replica si el nodo está en ACTIVE, STANDBY, o DRAINING
#   - Dirty flag se pone al appendar un evento, se limpia al replicar exitosamente
#   - PEERALIVETTLSEC=3.0s: peer se considera muerto si no hay last_seen en 3s
#   - Se llama en cada tick del worker (~1s) vía replicate_eventlog() y replicate_events()
#   - Falla silenciosamente si un peer no responde (no bloquea el tick)
#
# FRV-ID: 4e48ada454ba3669
# Header_End

import logging
import time
import requests

from cluster.runtime import context as ctx
from cluster.runtime.cluster_store import cluster_state
from cluster.runtime.registry import CLUSTER_REGISTRY
from cluster.runtime.event_log import (
    read_local_log_text,
    read_completed_log_text,
    write_replica_log,
    write_replica_events,
    write_completed_log,
    read_state,
    clear_eventlog_dirty_state,
    clear_events_dirty_state,

)
from cluster.runtime.state import NodeState
from cluster.utils.log_print import log_state

logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("requests").setLevel(logging.ERROR)

# =============================================================================
# Configuración de replicación
# =============================================================================

#: TTL en segundos para considerar un peer como vivo
#: Si no hay last_seen en este tiempo, el peer se excluye de replicación
PEERALIVETTLSEC = 3.0

#: Estados del nodo que permiten replicación
#: Solo ACTIVE, STANDBY, y DRAINING replican (no BOOT, ISOLATED, SEGMENTATION, OFFLINE)
REPLICATION_ALLOWED_STATES = {
    NodeState.ACTIVE.value,
    NodeState.STANDBY.value,
    NodeState.DRAINING.value,
}


def canonical_replica_node_id() -> str:
    """
    Devuelve el node_id canonical del nodo local para usar como nombre de replica.

    Returns:
        str: node_id del nodo local.

    Example:
        >>> canonical_replica_node_id()
        'lnx203hp'
    """
    return ctx.node_id


def alive_peer_ids():
    """
    Devuelve la lista de peers que están vivos (heartbeat reciente).

    Filtra cluster_state para incluir solo nodos que:
        1. No son el nodo local
        2. Han tenido actividad en los últimos PEERALIVETTLSEC segundos

    Returns:
        list[str]: node_ids de peers vivos, ordenados alfabéticamente.

    Example:
        >>> alive_peer_ids()
        ['lnx200nas', 'lnx204hp']

    Note:
        - Usa last_seen de cluster_state para determinar si está vivo
        - Si un peer no ha hecho heartbeat en 3s, se excluye
    """
    out = []
    now = time.time()
    for node_id, data in cluster_state.items():
        if node_id == ctx.node_id:
            continue
        if now - data.get("last_seen", 0) > PEERALIVETTLSEC:
            continue
        out.append(node_id)
    return sorted(set(out))


def configured_peer_ids():
    """
    Devuelve la lista de peers configurados (de ctx.peers y CLUSTER_REGISTRY).

    Combina:
        1. Peers de ctx.peers (configuración de bootstrap)
        2. Nodos de CLUSTER_REGISTRY (registros estáticos)

    Returns:
        list[str]: node_ids de peers configurados, ordenados alfabéticamente.

    Example:
        >>> configured_peer_ids()
        ['lnx200nas', 'lnx204hp']

    Note:
        - Excluye el nodo local
        - Deduplica con set()
    """
    out = []

    for peer in getattr(ctx, "peers", []) or []:
        peer_id = peer.get("node_id")
        if peer_id and peer_id != ctx.node_id:
            out.append(peer_id)

    for node_id in CLUSTER_REGISTRY.keys():
        if node_id != ctx.node_id:
            out.append(node_id)

    return sorted(set(out))


def target_peer_ids():
    """
    Devuelve la lista de peers objetivo para replicación (vivos OR configurados).

    Combina alive_peer_ids() y configured_peer_ids() con Unión.
    Esto asegura que se intenta replicar incluso a peers que están down
    (pueden recoverar más tarde).

    Returns:
        list[str]: node_ids de peers objetivo, ordenados alfabéticamente.

    Example:
        >>> target_peer_ids()
        ['lnx200nas', 'lnx204hp']

    Note:
        - Unión de peers vivos + configurados
        - Si un peer está configurado pero no está vivo, se iguala intentar replicar
          (fallará pero se intenta)
    """
    alive = alive_peer_ids()
    configured = configured_peer_ids()
    return sorted(set(alive) | set(configured))


def replicate_eventlog():
    """
    Replica el event log local a todos los peers.

    Secuencia:
        1. comprueba si el nodo está en un estado permitido (ACTIVE, STANDBY, DRAINING)
        2. comprueba si el log está dirty (modificado)
        3. lee el contenido del log local
        4. escribe el log como replica local
        5. envía POST /debug/log/replica/{node_id} a cada peer
        6. si todos los peers responden OK, limpia el dirty flag

    Note:
        - Se llama en cada tick del worker (~1s)
        - Falla silenciosamente si un peer no responde
        - El dirty flag se mantiene hasta que TODOS los peers confirmen
        - Solo replica si hay contenido (no replica logs vacíos)
    """

    node_id = canonical_replica_node_id()
    node_state = getattr(getattr(ctx, "node", None), "state", None)
    node_state_value = getattr(node_state, "value", None)

    state = read_state()
    dirty = bool(state.get("dirty", False))

    #log_state("cyan", "REPL TICK", f"node={node_id} dirty={dirty} ", 3)

    if node_state_value not in REPLICATION_ALLOWED_STATES:
        return

    #log_state("cyan", "REPL FLAG", f"dirty={dirty} state_exists={bool(state)}", 3)
    if not dirty:
        return

    content = read_local_log_text()
    completed_content = read_completed_log_text()

    if not content.strip():
        return

    write_replica_log(node_id, content)
    if completed_content.strip():
        write_completed_log(completed_content)

    peers = target_peer_ids()

    success = True

    for peer_id in peers:
        node = CLUSTER_REGISTRY.get(peer_id)
        if not node:
            success = False
            continue

        url = f"http://{node['host']}:{node['port']}/debug/log/replica/{node_id}"

        try:
            resp = requests.post(
                url,
                data=content.encode("utf-8"),
                headers={"Content-Type": "text/plain; charset=utf-8"},
                timeout=2,
            )

            if resp.ok:
                success = True
            else:
                success = False

        except Exception as e:
            success = False

    if success:
        clear_eventlog_dirty_state()


def replicate_events():
    """
    Replica los eventos completed (procesados) a todos los peers.

    Similar a replicate_eventlog() pero solo replica el completed log.
    Se usa para mantener una copia de eventos ya procesados en todos los nodos.

    Secuencia:
        1. comprueba si el nodo está en un estado permitido
        2. comprueba si el events log está dirty
        3. lee el completed log local
        4. escribe el events como replica local
        5. envía POST /debug/events/replica/{node_id} a cada peer
        6. si todos los peers responden OK, limpia el dirty flag

    Note:
        - Se llama en cada tick del worker (~1s)
        - Solo replica completed_content (eventos procesados)
        - Falla silenciosamente si un peer no responde
    """

    node_id = canonical_replica_node_id()
    node_state = getattr(getattr(ctx, "node", None), "state", None)
    node_state_value = getattr(node_state, "value", None)

    if node_state_value not in REPLICATION_ALLOWED_STATES:
        return

    state = read_state()
    dirty = bool(state.get("events_dirty", False))
    if not dirty:
        return

    completed_content = read_completed_log_text()

    write_replica_events(node_id, completed_content)
    if completed_content.strip():
        write_completed_log(completed_content)

    peers = target_peer_ids()

    success = True

    for peer_id in peers:
        node = CLUSTER_REGISTRY.get(peer_id)
        if not node:
            success = False
            continue

        url = f"http://{node['host']}:{node['port']}/debug/events/replica/{node_id}"

        try:
            resp = requests.post(
                url,
                data=completed_content.encode("utf-8"),
                headers={"Content-Type": "text/plain; charset=utf-8"},
                timeout=2,
            )

            if resp.ok:
                success = True
            else:
                success = False

        except Exception as e:
            success = False

    if success:
        clear_events_dirty_state()
