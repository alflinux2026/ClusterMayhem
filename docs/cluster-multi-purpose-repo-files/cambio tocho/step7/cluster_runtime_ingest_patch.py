from cluster.runtime.event_log import append_event
from cluster.utils.log_print import log_state
from cluster.runtime.events.event_state import EventStatus


def ingest_event(event, source_node_id: str):
    event.source_node = source_node_id
    event.mark_received()
    append_event(event)
    log_state("green", "[INGEST]", f"{event.event_id} from {source_node_id}", 3)
    return {"status": EventStatus.CREATED.value, "event_id": event.event_id}
