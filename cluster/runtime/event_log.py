import json
import time
import os
from typing import List

from cluster.runtime.events.cluster_event import ClusterEvent

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
LOG_PATH = os.path.join(BASE_DIR, "cluster", "data", "event_log.jsonl")


def ensure_dir():
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)


def append_event(event: ClusterEvent):
    ensure_dir()

    record = {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "schema_version": event.schema_version,
        "created_at": event.created_at,
        "received_at": event.received_at,
        "trace_id": event.trace_id,
        "source_node": event.source_node,
        "target_node": event.target_node,
        "route_hops": event.route_hops,
        "status": event.status,
        "attempt": event.attempt,
        "payload": event.payload,
    }

    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")


def load_events() -> List[dict]:
    if not os.path.exists(LOG_PATH):
        return []

    with open(LOG_PATH, "r") as f:
        return [json.loads(line) for line in f if line.strip()]


def replay_events(handler):
    """
    Re-ejecuta eventos contra un handler(event)
    """
    events = load_events()

    for raw in events:
        event = ClusterEvent(**raw)
        handler(event)
