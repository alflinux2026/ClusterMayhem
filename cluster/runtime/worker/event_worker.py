# =========================
# WORKER - IDEMPOTENT EXECUTOR
# =========================

import time
from cluster.runtime.event_log import append_event
from cluster.runtime.events.event_state import EventStatus


# -------------------------
# SIMPLE IDEMPOTENCY STORE (MVP)
# reemplazable por Redis / DB
# -------------------------
executed_keys = set()


# -------------------------
# BUSINESS EXECUTION PLACEHOLDER
# -------------------------
def run_business_logic(payload: dict):
    # Aquí va tu lógica real
    return {"ok": True, "payload": payload}


# -------------------------
# EXECUTE EVENT (IDEMPOTENT)
# -------------------------
def execute_event(event):

    # -------------------------
    # BUILD EXECUTION KEY
    # -------------------------
    event.execution_key = f"{event.event_id}:{event.attempt}"

    # -------------------------
    # IDEMPOTENCY CHECK
    # -------------------------
    if event.execution_key in executed_keys:
        return {
            "status": "cached",
            "event_id": event.event_id,
            "execution_key": event.execution_key
        }

    # -------------------------
    # EXECUTE BUSINESS LOGIC
    # -------------------------
    result = run_business_logic(event.payload)

    # -------------------------
    # MARK EXECUTION AS DONE
    # -------------------------
    executed_keys.add(event.execution_key)

    event.mark_status(EventStatus.COMPLETED)
    append_event(event)

    # -------------------------
    # RETURN RESULT
    # -------------------------
    return {
        "status": "completed",
        "event_id": event.event_id,
        "execution_key": event.execution_key,
        "result": result
    }
