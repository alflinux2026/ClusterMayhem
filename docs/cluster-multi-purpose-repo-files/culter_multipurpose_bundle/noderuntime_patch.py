from __future__ import annotations

import time
from typing import Any

from cluster.runtime.state import NodeState
from cluster.runtime.models import NodeRuntimeState
from cluster.runtime.eventlog import getlastappendmeta
from cluster.runtime.integrity import clusterintegrityreport, filesha256


class NodeRuntime:
    def __init__(self, nodeid: str, priority: int):
        self.nodeid = nodeid
        self.priority = priority
        self.runtime_state = NodeRuntimeState(
            node_id=nodeid,
            state=NodeState.BOOT,
            priority=priority,
        )

    @property
    def state(self) -> NodeState:
        return self.runtime_state.state

    @state.setter
    def state(self, newstate: NodeState) -> None:
        self.runtime_state.state = newstate
        self.runtime_state.touch()

    def transition(self, newstate: NodeState) -> None:
        if self.runtime_state.state == newstate:
            return
        self.runtime_state.state = newstate
        self.runtime_state.touch()

    def tick(self) -> None:
        if self.runtime_state.state == NodeState.BOOT:
            self.transition(NodeState.STANDBY)
            return

    def build_log_meta(self, log_path: str) -> dict[str, Any]:
        size = 0
        try:
            from os import path as osp
            size = osp.getsize(log_path) if osp.exists(log_path) else 0
        except OSError:
            size = 0
        return {
            **getlastappendmeta(),
            "log_size": size,
            "file_size": size,
            "file_hash": filesha256(log_path),
        }

    def build_heartbeat(self, log_path: str, streams: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
        clusterint = clusterintegrityreport()
        self.runtime_state.log_meta = self.build_log_meta(log_path)
        self.runtime_state.cluster_integrity = clusterint
        self.runtime_state.active_streams = streams or {}
        return {
            "node_id": self.runtime_state.node_id,
            "state": self.runtime_state.state.value,
            "priority": self.runtime_state.priority,
            "ts": time.time(),
            "log_meta": self.runtime_state.log_meta,
            "cluster_integrity": self.runtime_state.cluster_integrity,
            "streams": self.runtime_state.active_streams,
        }
