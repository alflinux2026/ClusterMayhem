# File: ./cluster/runtime/state.py
# Previous: none
# Author: alftorres
# Date: 2026-05-28T17:11:50+0200
# Version: 0.0.0
# Genealogy:
#   ./cluster/runtime/state.py 0.0.0 2026-05-28T17:11:50+0200
#   God
#
# Purpose:
#   Definición de estados del nodo y transiciones de estado.
#   Define la máquina de estados finitos (FSM) que controla el ciclo de vida
#   de un nodo en el cluster: BOOT -> DISCOVERING -> STANDBY -> ACTIVE, etc.
#   También proporciona funciones para transicionar entre estados y calcular
#   la antigüedad del estado actual.
# Notes:
#   - Estados principales: BOOT -> DISCOVERING -> STANDBY -> ACTIVE
#   - Estados especiales: SEGMENTATION (rotación de logs), DRAINING (preparando segmentación),
#                        ISOLATED (sleep/pausa), OFFLINE (desconectado)
#   - Cada estado tiene: state_since (timestamp), prev_state, state_reason
#   - Se usa en node_runtime.py y node_worker.py para controlar el ciclo de vida
#   - No hay validación estricta de transiciones válidas (se permite cualquier transición)
#
# FRV-ID: 606b01b5d3a56e66
# Header_End

# state.py
import time
from enum import Enum


class NodeState(str, Enum):
    """
    Estados del nodo en el cluster.

    Ciclo de vida típico:
        BOOT -> DISCOVERING -> STANDBY -> ACTIVE

    Estados especiales:
        - SEGMENTATION: rotando archivos de log (segmentación)
        - DRAINING: esperando a que no haya eventos pendientes antes de segmentar
        - ISOLATED: nodo pausado/sleep (no procesa eventos)
        - OFFLINE: nodo desconectado (no responde)

    Example:
        >>> NodeState.ACTIVE
        <NodeState.ACTIVE: 'ACTIVE'>

        >>> NodeState.ACTIVE.value
        'ACTIVE'

        >>> str(NodeState.STANDBY)
        'STAND-BY'

    Note:
        - Hereda de str para poder comparar directamente con strings
        - value es el nombre del estado en mayúsculas (excepto STANDBY -> "STAND-BY")
    """
    BOOT = "BOOT"
    DISCOVERING = "DISCOVERING"
    STANDBY = "STAND-BY"
    ACTIVE = "ACTIVE"
    SEGMENTATION = "SEGMENTATION"
    DRAINING = "DRAINING"
    ISOLATED = "ISOLATED"
    OFFLINE = "OFFLINE"


def _state_value(value):
    """
    Extrae el valor string de un estado.

    Convierte un NodeState (enum) a su valor string, o deja el string tal cual
    si ya es string.

    Args:
        value: NodeState enum o string.

    Returns:
        str: El valor string del estado.

    Example:
        >>> _state_value(NodeState.ACTIVE)
        'ACTIVE'

        >>> _state_value("ACTIVE")
        'ACTIVE'
    """
    return value.value if isinstance(value, Enum) else str(value)


def ensure_state_meta(node, now=None):
    """
    Asegura que el nodo tiene los metadatos de estado iniciales.

    Añade los atributos si no existen:
        - state_since: timestamp cuando se entró al estado actual
        - prev_state: estado anterior (None si es el primero)
        - state_reason: razón de la última transición

    Args:
        node: Objeto nodo (tiene atributo state).
        now: Timestamp opcional. Si no se proporciona, usa time.time().

    Returns:
        Node: El mismo nodo con los metadatos asegurados.

    Example:
        >>> class Node:
        ...     state = NodeState.ACTIVE
        >>> node = Node()
        >>> ensure_state_meta(node)
        >>> node.state_since
        1779956226.123
        >>> node.prev_state
        None
        >>> node.state_reason
        None

    Note:
        - Solo añade los atributos si no existen (no sobrescribe)
        - Se llama antes de calcular state_age o transicionar
    """
    now = now or time.time()

    if not hasattr(node, "state_since") or node.state_since is None:
        node.state_since = now

    if not hasattr(node, "prev_state"):
        node.prev_state = None

    if not hasattr(node, "state_reason"):
        node.state_reason = None

    return node


def transition_node_state(node, new_state, reason=None, now=None):
    """
    Transiciona un nodo a un nuevo estado.

    Actualiza los metadatos de estado (prev_state, state_since, state_reason)
    solo si el estado cambia. Si el estado es el mismo pero hay reason,
    actualiza solo el reason.

    Args:
        node: Objeto nodo con atributo state.
        new_state: Nuevo estado (NodeState enum o string).
        reason: Razón de la transición (ej: "leader_selected", "sleep_command").
        now: Timestamp opcional. Si no se proporciona, usa time.time().

    Returns:
        dict: Información sobre la transición:
            - changed: bool, si el estado cambió
            - old_state: str, estado anterior
            - new_state: str, nuevo estado
            - state_since: float, timestamp del estado
            - state_reason: str | None, razón de la transición

    Example:
        >>> class Node:
        ...     state = NodeState.STANDBY
        >>> node = Node()
        >>> transition_node_state(node, NodeState.ACTIVE, reason="leader_selected")
        {'changed': True, 'old_state': 'STAND-BY', 'new_state': 'ACTIVE',
         'state_since': 1779956226.123, 'state_reason': 'leader_selected'}

        >>> transition_node_state(node, NodeState.ACTIVE, reason="still_leader")
        {'changed': False, 'old_state': 'ACTIVE', 'new_state': 'ACTIVE',
         'state_since': 1779956226.123, 'state_reason': 'still_leader'}

    Note:
        - Si el estado no cambia pero hay reason, se actualiza solo el reason
        - Si el nodo no tiene state_since, se inicializa al primer call
        - Se usa en NodeRuntime.transition() y NodeWorker.tick_*()
    """
    now = now or time.time()
    ensure_state_meta(node, now=now)

    old_state = _state_value(node.state)
    new_state_value = _state_value(new_state)

    changed = old_state != new_state_value

    if changed:
        node.prev_state = old_state
        node.state = new_state if isinstance(new_state, Enum) else NodeState(new_state_value)
        node.state_since = now
        node.state_reason = reason
    else:
        if reason is not None:
            node.state_reason = reason

    return {
        "changed": changed,
        "old_state": old_state,
        "new_state": _state_value(node.state),
        "state_since": node.state_since,
        "state_reason": node.state_reason,
    }


def get_state_age_s(node, now=None):
    """
    Calcula la antigüedad del estado actual del nodo en segundos.

    Args:
        node: Objeto nodo con atributo state_since.
        now: Timestamp opcional. Si no se proporciona, usa time.time().

    Returns:
        float: Segundos desde que se entró al estado actual (mínimo 0.0).

    Example:
        >>> class Node:
        ...     state_since = 1779956226.0
        >>> node = Node()
        >>> get_state_age_s(node, now=1779956256.0)
        30.0

        >>> get_state_age_s(node, now=1779956226.0)
        0.0

    Note:
        - Asegura metadatos antes de calcular (llama a ensure_state_meta)
        - Retorna máximo 0.0 (nunca negativo)
        - Se usa en logs para mostrar "age=35.9s" del estado
    """
    now = now or time.time()
    ensure_state_meta(node, now=now)
    return max(0.0, now - float(node.state_since))
