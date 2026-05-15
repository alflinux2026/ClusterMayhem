from pydantic import BaseModel
from typing import Dict, Any
import time
import uuid


class ClusterEvent(BaseModel):
    event_id: str | None = None
    type: str
    payload: Dict[str, Any]
    created_at: float | None = None


def normalize_event(event: ClusterEvent):
    event.event_id = event.event_id or str(uuid.uuid4())
    event.created_at = event.created_at or time.time()
    return event
