# =========================
# WORKER - IDEMPOTENT EXECUTOR
# =========================

import time
from cluster.runtime.event_log import append_event
from cluster.runtime.events.event_state import EventStatus
from cluster.utils.log_print import log_state


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

    #log_state("red", "[EXECUTE entry ...]", event.event_id, 3)


    # -------------------------
    # BUILD EXECUTION KEY
    # -------------------------
    event.execution_key = f"{event.event_id}:{event.attempt}"

    #log_state("red", "[EXECUTION KEY]", event.execution_key, 3)
    #log_state("red", "[EXECUTED KEYS SIZE]", str(len(executed_keys)), 3)

    # -------------------------
    # IDEMPOTENCY CHECK NO FUNCIONA
    # -------------------------

    if event.execution_key in executed_keys:
        log_state("red", "[CACHE HIT]", event.execution_key, 3)
        return {
            "status": "completed",
            "cached": True,
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

    log_state("green", "[EXECUTE]", event.event_id, 3)

#    event.mark_status(EventStatus.COMPLETED)

#    log_state("yellow", "[STATE]", f"{event.event_id} -> EVENT COMPLETED", 3)

#    append_event(event)

    # -------------------------
    # RETURN RESULT
    # -------------------------
    return {
        "status": "completed",
        "event_id": event.event_id,
        "execution_key": event.execution_key,
        "result": result
    }
