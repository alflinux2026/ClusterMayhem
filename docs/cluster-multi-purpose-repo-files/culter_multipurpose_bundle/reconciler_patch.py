from __future__ import annotations

import time
from collections import defaultdict

from cluster.runtime.eventlog import load_events, append_event
from cluster.runtime.models import EventEnvelope, EventStatus

EXECUTIONTIMEOUT = 10.0


def reconciletick(noderuntime) -> None:
    if noderuntime.state.value != "ACTIVE":
        return
    streams = getattr(noderuntime.runtime_state, "active_streams", {})
    for meta in streams.values():
        stream = meta.get("stream")
        if stream is None:
            continue
        events = load_events(stream)
        byid = defaultdict(list)
        for e in events:
            byid[e.event_id].append(e)
        if not byid:
            continue
        now = time.time()
        for eid, history in byid.items():
            history.sort(key=lambda x: x.updated_at or x.created_at or 0)
            latest = history[-1]
            if latest.status in (EventStatus.COMPLETED, EventStatus.FAILED):
                continue
            if latest.status == EventStatus.EXECUTING:
                lastupdate = latest.updated_at or latest.created_at or 0
                if now - lastupdate > EXECUTIONTIMEOUT:
                    recovered = EventEnvelope(
                        stream=latest.stream,
                        event_type=latest.event_type,
                        payload=latest.payload,
                        event_id=latest.event_id,
                        trace_id=latest.trace_id,
                        status=EventStatus.CREATED,
                        route_hops=list(latest.route_hops),
                        source_node=latest.source_node,
                        target_node=None,
                        execution_key=None,
                        created_at=latest.created_at,
                        updated_at=now,
                        received_at=latest.received_at,
                        attempt=0,
                    )
                    append_event(recovered)
