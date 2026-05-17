from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
import time
import uuid

from cluster.runtime.events.event_state import EventStatus

from cluster.runtime.events.event_state import (
    EventStatus,
    validate_transition,
)

class ClusterEvent(BaseModel):
    """
    Canonical event model for Mayhem Cluster
    Immutable core + append-only metadata
    """

    # -------------------------
    # IDENTITY
    # -------------------------
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str

    schema_version: int = Field(default=1)

    # -------------------------
    # TIMING
    # -------------------------
    created_at: float = Field(default_factory=time.time)
    received_at: Optional[float] = None

    # -------------------------
    # TRACE
    # -------------------------
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_event_id: Optional[str] = None

    source_node: Optional[str] = None

    # -------------------------
    # ROUTING
    # -------------------------
    target_node: Optional[str] = None
    route_hops: List[str] = Field(default_factory=list)

    # -------------------------
    # STATE
    # -------------------------


    status: EventStatus = EventStatus.CREATED

    attempt: int = 0

    # -------------------------
    # PAYLOAD
    # -------------------------
    payload: Dict[str, Any] = Field(default_factory=dict)

    # -------------------------
    # HELPERS
    # -------------------------
    def mark_received(self):
        self.received_at = time.time()



    def mark_status(self, status: EventStatus):
        validate_transition(self.status, status)
        self.status = status

    def add_hop(self, hop: str):
        self.route_hops.append(hop)
