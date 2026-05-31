# File: ./cluster/runtime/events/event_state.py
# Previous: none
# Author: alftorres
# Date: 2026-05-28T17:09:28+0200
# Version: 0.0.0
# Genealogy:
#   ./cluster/runtime/events/event_state.py 0.0.0 2026-05-28T17:09:28+0200
#   God
#
# Purpose:
#   Definición de estados de eventos y transiciones válidas.
#   Define la máquina de estados finitos (FSM) para el ciclo de vida de un evento:
#     CREATED -> EXECUTING -> COMPLETED o FAILED
#   También valida que las transiciones entre estados sean válidas.
# Notes:
#   - CREATED: evento recién creado, esperando ser ejecutado
#   - EXECUTING: evento en ejecución (business logic se está ejecutando)
#   - COMPLETED: evento ejecutado exitosamente
#   - FAILED: evento fallido (no se reintentará automáticamente)
#   - VALID_TRANSITIONS define qué transiciones son permitidas
#   - validate_transition() levanta ValueError si la transición es inválida
#   - Transiciones idempotentes (old == new) son sempre válidas (NO-OP)
#
# FRV-ID: 0aa52064e4460767
# Header_End

from enum import Enum


class EventStatus(str, Enum):
    """
    Estados de un evento en el cluster.

    Ciclo de vida típico:
        CREATED -> EXECUTING -> COMPLETED

    O en caso de error:
        CREATED -> EXECUTING -> FAILED

    Attributes:
        CREATED: Evento recién creado, esperando ser ejecutado.
        EXECUTING: Evento en ejecución (business logic se está ejecutando).
        COMPLETED: Evento ejecutado exitosamente.
        FAILED: Evento fallido (no se reintentó o falló el retry).

    Example:
        >>> EventStatus.CREATED
        <EventStatus.CREATED: 'created'>

        >>> EventStatus.CREATED.value
        'created'

        >>> str(EventStatus.COMPLETED)
        'completed'

    Note:
        - Hereda de str para poder comparar directamente con strings
        - value es el nombre del estado en minúsculas
    """
    CREATED = "created"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


    """
    Máquina de estados de evento.

    Defines qué transiciones entre estados son permitidas:
        - CREATED -> EXECUTING: iniciar ejecución
        - EXECUTING -> COMPLETED: ejecución exitosa
        - EXECUTING -> FAILED: ejecución fallida
        - EXECUTING -> CREATED: retry (volver a empezar)
        - COMPLETED -> cualquiera: NO (evento ya completado, inmutable)
        - FAILED -> cualquiera: NO (evento fallido, inmutable)

    Example:
        >>> VALID_TRANSITIONS[EventStatus.CREATED]
        [<EventStatus.EXECUTING: 'executing'>]

        >>> VALID_TRANSITIONS[EventStatus.EXECUTING]
        [<EventStatus.COMPLETED: 'completed'>, <EventStatus.FAILED: 'failed'>, <EventStatus.CREATED: 'created'>]
    """

    # Transiciones válidas entre estados de evento

VALID_TRANSITIONS = {
    EventStatus.CREATED: [
        EventStatus.EXECUTING,
    ],

    EventStatus.EXECUTING: [
        EventStatus.COMPLETED,
        EventStatus.FAILED,
        EventStatus.CREATED,  # retry
    ],

    EventStatus.COMPLETED: [],

    EventStatus.FAILED: [],
}


def validate_transition(old_status, new_status):
    """
    Valida que una transición entre estados sea válida.

    Args:
        old_status: Estado actual (EventStatus enum).
        new_status: Nuevo estado (EventStatus enum).

    Raises:
        ValueError: Si la transición no está permitida.

    Example:
        >>> validate_transition(EventStatus.CREATED, EventStatus.EXECUTING)
        # OK (no levanta exception)

        >>> validate_transition(EventStatus.CREATED, EventStatus.COMPLETED)
        ValueError: Invalid transition: created -> completed

        >>> validate_transition(EventStatus.COMPLETED, EventStatus.COMPLETED)
        # OK (idempotent NO-OP)

    Note:
        - Transiciones idempotentes (old == new) siempre son válidas (NO-OP)
        - Si old_status no está en VALID_TRANSITIONS, retorna allowed=[] (ninguna transición válida)
    """
    if old_status == new_status:
        return  # IDEMPOTENTE NO-OP

    allowed = VALID_TRANSITIONS.get(old_status, [])

    if new_status not in allowed:
        raise ValueError(
            f"Invalid transition: {old_status} -> {new_status}"
        )
