from __future__ import annotations

import time
from typing import Iterable

from cluster.runtime import context as ctx
from cluster.runtime.eventlog import getcreatedevents, getcompletedeventids, append_event
from cluster.runtime.eventrouter import forwardevent
from cluster.runtime.leader import computeleader, computealive
from cluster.runtime.models import EventEnvelope, EventStatus
from cluster.utils.logprint import logstate

DISPATCHALIVETIMEOUT = 1.5


def _iter_created_events() -> list[EventEnvelope]:
    streams = getattr(ctx.node.runtime_state, "active_streams", {}) if getattr(ctx, "node", None) else {}
    out: list[EventEnvelope] = []
    for stream_id, meta in streams.items():
        stream = meta.get("stream")
        if stream is None:
            continue
        out.extend(getcreatedevents(stream))
    return out


def dispatchtick() -> None:
    if computeleader() != ctx.nodeid:
        return
    events = _iter_created_events()
    if not events:
        return
    logstate("magenta", "DISPATCH", f"len={len(events)}", 3)
    for event in events:
        dispatchcreatedevent(event)


def dispatchcreatedevent(event: EventEnvelope) -> None:
    completed = set(getcompletedeventids(event.stream))
    if event.event_id in completed:
        logstate("red", "SKIP COMPLETED", event.event_id, 3)
        return
    alive = computealive(DISPATCHALIVETIMEOUT, includeself=True)
    if not alive:
        logstate("red", "NO ALIVE NODES", event.event_id, 3)
        return
    target = min(alive.items(), key=lambda x: (x[1].priority, x[0]))[0]
    event.target_node = target
    event.add_hop("dispatcher-target")
    event.attempt = event.attempt or 0
    event.attempt += 1
    event.mark_status(EventStatus.EXECUTING)
    event.updated_at = time.time()
    append_event(event)
    forwardevent(target, event)
