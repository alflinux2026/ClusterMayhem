from pydantic import BaseModel, Field
from typing import Optional
from uuid import uuid4
import time

from cluster.runtime.events.event_state import EventStatus


class ClusterEvent(BaseModel):

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    trace_id: str = Field(default_factory=lambda: str(uuid4()))

    schema_version: str = "0.1"   # 👈 FIJO: string ONLY

    event_type: str

    payload: dict = {}

    status: EventStatus = EventStatus.CREATED

    route_hops: list[str] = []

    target_node: Optional[str] = None
    source_node: Optional[str] = None   # 👈 LO USA event_log

    created_at: float = 0.0
    updated_at: float = 0.0

    received_at: Optional[float] = None  # 👈 LO USA event_log

    attempt: int = 0

    execution_key: Optional[str] = None  # 👈 LO USA worker

    # -------------------------
    # HELPERS
    # -------------------------

    def add_hop(self, hop: str):
        self.route_hops.append(hop)

    def mark_status(self, status: EventStatus):
        self.status = status

    def mark_received(self):
        self.received_at = time.time()
