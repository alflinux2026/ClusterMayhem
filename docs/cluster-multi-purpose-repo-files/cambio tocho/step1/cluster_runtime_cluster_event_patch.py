from pydantic import BaseModel, Field
from typing import Optional
from uuid import uuid4
import time

from cluster.runtime.events.event_state import EventStatus


class ClusterEvent(BaseModel):
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
        self.route_hops.append(hop)
        self.updated_at = time.time()

    def mark_status(self, status: EventStatus):
        self.status = status
        self.updated_at = time.time()

    def mark_received(self):
        self.received_at = time.time()
        self.updated_at = self.received_at
