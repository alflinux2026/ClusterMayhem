from enum import Enum


class EventStatus(str, Enum):
    CREATED = "created"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


VALID_TRANSITIONS = {
    EventStatus.CREATED: [
        EventStatus.EXECUTING,
    ],

    EventStatus.EXECUTING: [
        EventStatus.COMPLETED,
        EventStatus.FAILED,
        EventStatus.CREATED,  # retry
    ],

    EventStatus.COMPLETED: [],

    EventStatus.FAILED: [],
}


def validate_transition(old_status, new_status):
    allowed = VALID_TRANSITIONS.get(old_status, [])

    if new_status not in allowed:
        raise ValueError(
            f"Invalid transition: {old_status} -> {new_status}"
        )
