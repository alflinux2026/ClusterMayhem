# File: ./cluster/runtime/events/cluster_event.py
# Previous: none
# Author: alftorres
# Date: 2026-05-28T17:09:05+0200
# Version: 0.0.0
# Genealogy:
#   ./cluster/runtime/events/cluster_event.py 0.0.0 2026-05-28T17:09:05+0200
#   God
#
# Purpose:
#   Modelo de dato de evento del cluster.
#   ClusterEvent es el objeto que representa un evento en el sistema,
#   con todos los metadatos necesarios para routing, tracking, y state management.
#   Hereda de Pydantic BaseModel para validación automática y serialization.
# Notes:
#   - event_id y trace_id se generan automáticamente con uuid4()
#   - status es un EventStatus (CREATED, EXECUTING, COMPLETED, FAILED)
#   - route_hops trackea el path del evento a través del cluster (para debugging)
#   - target_node y source_node para routing entre nodos
#   - created_at, updated_at, received_at para tracking temporal
#   - attempt y execution_key para retries y deduplication
#   - add_hop(), mark_status(), mark_received() actualizan updated_at automáticamente
#
# FRV-ID: 317a6125cc88cfcb
# Header_End

from pydantic import BaseModel, Field
from typing import Optional
from uuid import uuid4
import time

from cluster.runtime.events.event_state import EventStatus


class ClusterEvent(BaseModel):
    """
    Evento del cluster.

    Objeto de dato que representa un evento en el sistema distribuido.
    Incluye metadatos para routing, tracking, state management, y debugging.

    Attributes:
        event_id (str): ID único del evento (UUID v4, auto-generado).
        trace_id (str): ID de traza para correlación (UUID v4, auto-generado).
        schema_version (str): Versión del schema del evento (default: "0.1").
        event_type (str): Tipo del evento (ej: "user_command", "timer", "webhook").
        payload (dict): Datos del evento (business payload).
        status (EventStatus): Estado actual (CREATED, EXECUTING, COMPLETED, FAILED).
        route_hops (list[str]): Lista de nodos por donde pasó el evento.
        target_node (str | None): Nodo destino del evento.
        source_node (str | None): Nodo origen del evento.
        created_at (float): Timestamp cuando se creó el evento.
        updated_at (float): Timestamp de la última actualización.
        received_at (float | None): Timestamp cuando se recibió el evento.
        attempt (int): Número de intentos de ejecución (para retries).
        execution_key (str | None): Key para deduplication de ejecución.

    Example:
        >>> event = ClusterEvent(
        ...     event_type="user_command",
        ...     payload={"msg": "hola", "data": {"foo": "bar"}}
        ... )
        >>> event.event_id
        'a1b2c3d4-...'
        >>> event.status
        <EventStatus.CREATED: 'created'>

        >>> event.mark_status(EventStatus.EXECUTING)
        >>> event.status
        <EventStatus.EXECUTING: 'executing'>

        >>> event.add_hop("lnx203hp")
        >>> event.route_hops
        ['lnx203hp']

    Note:
        - Hereda de Pydantic BaseModel: validación automática, .model_dump(), .model_json()
        - event_id y trace_id se generan con default_factory=lambda: str(uuid4())
        - payload es un dict vacío por defecto (default_factory=dict)
        - route_hops es una lista vacía por defecto (default_factory=list)
    """
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    trace_id: str = Field(default_factory=lambda: str(uuid4()))

    schema_version: str = "0.1"
    event_type: str

    payload: dict = Field(default_factory=dict)

    status: EventStatus = EventStatus.CREATED

    route_hops: list[str] = Field(default_factory=list)

    target_node: Optional[str] = None
    source_node: Optional[str] = None

    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    received_at: Optional[float] = None

    attempt: int = 0
    execution_key: Optional[str] = None

    def add_hop(self, hop: str):
        """
        Añade un hop al route_hops (tracking de routing).

        Args:
            hop: node_id del nodo por donde pasó el evento.

        Example:
            >>> event = ClusterEvent(event_type="test")
            >>> event.route_hops
            []
            >>> event.add_hop("lnx203hp")
            >>> event.route_hops
            ['lnx203hp']
            >>> event.add_hop("lnx200nas")
            >>> event.route_hops
            ['lnx203hp', 'lnx200nas']

        Note:
            - Actualiza updated_at al añadir el hop
            - Se usa para debugging de routing en cluster
        """
        self.route_hops.append(hop)
        self.updated_at = time.time()

    def mark_status(self, status: EventStatus):
        """
        Marca el estado del evento.

        Args:
            status: Nuevo estado (EventStatus enum).

        Example:
            >>> event = ClusterEvent(event_type="test")
            >>> event.status
            <EventStatus.CREATED: 'created'>
            >>> event.mark_status(EventStatus.EXECUTING)
            >>> event.status
            <EventStatus.EXECUTING: 'executing'>
            >>> event.mark_status(EventStatus.COMPLETED)
            >>> event.status
            <EventStatus.COMPLETED: 'completed'>

        Note:
            - Actualiza updated_at al cambiar el estado
            - No valida la transición (usa validate_transition() si hace falta)
        """
        self.status = status
        self.updated_at = time.time()

    def mark_received(self):
        """
        Marca el timestamp cuando se recibió el evento.

        Sets received_at = time.time() y updated_at = received_at.

        Example:
            >>> event = ClusterEvent(event_type="test")
            >>> event.received_at
            None
            >>> event.mark_received()
            >>> event.received_at
            1779956226.123
        Note:
            - Se llama en ingest_event() cuando se ingiere el evento
        """
        self.received_at = time.time()
        self.updated_at = self.received_at
