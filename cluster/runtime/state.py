from enum import Enum

class NodeState(str, Enum):
    BOOT = "BOOT"
    DISCOVERING = "DISCOVERING"
    STANDBY = "STANDBY"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    ISOLATED = "ISOLATED"
    OFFLINE = "OFFLINE"