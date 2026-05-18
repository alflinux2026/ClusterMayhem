from enum import Enum

class NodeState(str, Enum):
    BOOT = "BOOT"
    DISCOVERING = "DISCOVERING"
    STANDBY = "STAND-BY"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    ISOLATED = "ISOLATED"
    OFFLINE = "OFFLINE"
