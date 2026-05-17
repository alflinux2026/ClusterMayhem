import json
import os
from typing import List

from cluster.runtime.events.cluster_event import ClusterEvent
from cluster.runtime.events.event_state import EventStatus

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
LOG_PATH = os.path.join(BASE_DIR, "cluster", "data", "event_log.local.jsonl")


def get_latest_event(event_id: str):
    events = load_events()

    for e in reversed(events):
        if e["event_id"] == event_id:
            return e

    return None

# =========================
# LOAD EVENTS
# =========================
def load_events() -> List[dict]:
    if not os.path.exists(LOG_PATH):
        return []

    with open(LOG_PATH, "r") as f:
        return [json.loads(line) for line in f if line.strip()]


# =========================
# ENSURE DIR
# =========================
def ensure_dir():
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)


# =========================
# NORMALIZE RAW EVENT
# =========================
def _normalize_event(e: dict) -> dict:
    e["schema_version"] = str(e.get("schema_version", "0.1"))
    e.setdefault("received_at", None)
    e.setdefault("attempt", 0)
    e.setdefault("route_hops", [])
    return e


# =========================
# GET CREATED EVENTS
# =========================
def get_created_events():
    events = load_events()

    latest = {}

    for e in events:
        e["schema_version"] = str(e.get("schema_version", "0.1"))
        e.setdefault("received_at", None)
        e.setdefault("attempt", 0)
        e.setdefault("route_hops", [])
        e.setdefault("execution_key", None)
        latest[e["event_id"]] = e

    events = [
        ClusterEvent(**e)
        for e in latest.values()
    ]

    return [
        e for e in events
        if e.status == EventStatus.CREATED
    ]


# =========================
# GET COMPLETED IDS
# =========================
def get_completed_event_ids():

    events = load_events()

    latest = {}

    for e in events:
        latest[e["event_id"]] = e

    domain_events = [
        ClusterEvent(**_normalize_event(e))
        for e in latest.values()
    ]

    return {
        e.event_id
        for e in domain_events
        if e.status == EventStatus.COMPLETED
    }


# =========================
# APPEND EVENT
# =========================
def append_event(event: ClusterEvent):
    ensure_dir()

    record = {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "schema_version": str(event.schema_version),
        "created_at": event.created_at,
        "received_at": getattr(event, "received_at", None),
        "trace_id": event.trace_id,
        "target_node": event.target_node,
        "route_hops": event.route_hops,
        "status": event.status,
        "attempt": event.attempt,
        "payload": event.payload,
    }

    # dedup guard
    if event.status == EventStatus.COMPLETED:
        existing = load_events()
        if any(
            e["event_id"] == event.event_id and
            e["status"] == EventStatus.COMPLETED.value
            for e in existing
        ):
            return

    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")


# =========================
# REPLAY
# =========================
def replay_events(handler):
    """
    Re-ejecuta eventos contra un handler(event)
    """
    events = load_events()

    for raw in events:
        event = ClusterEvent(**_normalize_event(raw))
        handler(event)
