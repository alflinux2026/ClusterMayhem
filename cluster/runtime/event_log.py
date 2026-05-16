import json
import time
import os
from typing import List

from cluster.runtime.events.cluster_event import ClusterEvent

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
LOG_PATH = os.path.join(BASE_DIR, "cluster", "data", "event_log.local.jsonl")



def get_created_events():

    events = load_events()

    # -------------------------
    # LAST STATE BY EVENT
    # -------------------------

    latest = {}

    for e in events:
        latest[e["event_id"]] = e

    # -------------------------
    # FILTER CREATED
    # -------------------------

    created = []

    for e in latest.values():

        if e.get("status") == "created":

            created.append(
                ClusterEvent(**e)
            )

    return created


def get_completed_event_ids():

    events = load_events()

    return {
        e["event_id"]
        for e in events
        if e.get("status") == "completed"
    }

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

    # 🚨 dedup guard
    if event.status == "completed":
        existing = load_events()
        if any(e["event_id"] == event.event_id and e["status"] == "completed" for e in existing):
            return

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
