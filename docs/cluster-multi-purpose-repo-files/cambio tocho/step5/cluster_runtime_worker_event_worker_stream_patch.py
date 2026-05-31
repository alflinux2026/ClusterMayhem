from cluster.runtime.event_log import append_event
from cluster.runtime.events.event_state import EventStatus
from cluster.utils.log_print import log_state

executed_keys = set()


def run_business_logic(payload: dict):
    return {"ok": True, "payload": payload}


def execute_event(event, stream=None):
    event.execution_key = f"{event.event_id}:{event.attempt}"

    if event.execution_key in executed_keys:
        log_state("red", "[CACHE HIT]", event.execution_key, 3)
        return {
            "status": "completed",
            "cached": True,
            "event_id": event.event_id,
            "execution_key": event.execution_key,
        }

    result = run_business_logic(event.payload)
    executed_keys.add(event.execution_key)

    msg = event.payload.get("msg", "<no-msg>")
    log_state("green", "[EXECUTE]", f"{msg:12}", 3)

    event.mark_status(EventStatus.COMPLETED)
    append_event(event)

    return {
        "status": "completed",
        "event_id": event.event_id,
        "execution_key": event.execution_key,
        "result": result,
    }
