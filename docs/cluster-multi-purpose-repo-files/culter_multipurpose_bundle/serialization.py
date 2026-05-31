from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .models import EventEnvelope, EventStatus, HeartbeatState, SegmentMeta, StreamKey, NodeRuntimeState


def event_to_record(event: EventEnvelope) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "trace_id": event.trace_id,
        "stream_id": event.stream.stream_id(),
        "tenant_id": event.stream.tenant_id,
        "app_id": event.stream.app_id,
        "data_type": event.stream.data_type,
        "schema_version": event.stream.schema_version,
        "event_type": event.event_type,
        "payload": event.payload,
        "status": event.status.value,
        "route_hops": event.route_hops,
        "source_node": event.source_node,
        "target_node": event.target_node,
        "execution_key": event.execution_key,
        "created_at": event.created_at,
        "updated_at": event.updated_at,
        "received_at": event.received_at,
        "attempt": event.attempt,
    }


def record_to_event(record: dict[str, Any]) -> EventEnvelope:
    stream = StreamKey(
        tenant_id=record["tenant_id"],
        app_id=record["app_id"],
        data_type=record["data_type"],
        schema_version=record.get("schema_version", "v1"),
    )
    event = EventEnvelope(
        stream=stream,
        event_type=record.get("event_type", ""),
        payload=record.get("payload", {}),
        event_id=record.get("event_id"),
        trace_id=record.get("trace_id"),
        status=EventStatus(record.get("status", EventStatus.CREATED.value)),
        route_hops=record.get("route_hops", []),
        source_node=record.get("source_node"),
        target_node=record.get("target_node"),
        execution_key=record.get("execution_key"),
        created_at=record.get("created_at", 0.0),
        updated_at=record.get("updated_at", 0.0),
        received_at=record.get("received_at"),
        attempt=record.get("attempt", 0),
    )
    return event


def segment_meta_to_record(meta: SegmentMeta) -> dict[str, Any]:
    data = asdict(meta)
    data["stream_id"] = meta.stream.stream_id()
    data["tenant_id"] = meta.stream.tenant_id
    data["app_id"] = meta.stream.app_id
    data["data_type"] = meta.stream.data_type
    data["schema_version"] = meta.stream.schema_version
    return data


def heartbeat_to_record(hb: HeartbeatState) -> dict[str, Any]:
    return hb.to_record()
