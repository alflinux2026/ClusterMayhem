from dataclasses import dataclass, field
import os
import time
import requests

from cluster.runtime.state import NodeState
from cluster.runtime.leader import compute_leader
from cluster.runtime.event_log import get_last_append_meta, load_events
from cluster.runtime.integrity import file_sha256, cluster_integrity_report
from cluster.utils.log_print import log_state


@dataclass(slots=True)
class NodeRuntimeState:
    node_id: str
    state: NodeState
    priority: int
    last_seen: float = field(default_factory=time.time)
    log_meta: dict = field(default_factory=dict)
    cluster_integrity: dict = field(default_factory=dict)
    active_streams: dict = field(default_factory=dict)

    def touch(self):
        self.last_seen = time.time()


class NodeRuntime:
    def __init__(self, node_id, priority):
        self.runtime_state = NodeRuntimeState(node_id=node_id, state=NodeState.BOOT, priority=priority)
        self.last_heartbeat = time.time()

    @property
    def node_id(self):
        return self.runtime_state.node_id

    @property
    def priority(self):
        return self.runtime_state.priority

    @property
    def state(self):
        return self.runtime_state.state

    @state.setter
    def state(self, new_state):
        self.runtime_state.state = new_state
        self.runtime_state.touch()

    def transition(self, new_state):
        if self.runtime_state.state == new_state:
            return
        print(f"[{self.node_id}] {self.runtime_state.state} -> {new_state}")
        self.state = new_state

    def tick(self):
        if self.state == NodeState.BOOT:
            self.transition(NodeState.STANDBY)
            return

        leader = compute_leader()
        if leader == self.node_id:
            if self.state == NodeState.STANDBY:
                log_state("yellow", "[CLUSTER]", f"[{self.node_id}] becoming ACTIVE", 3)
                self.transition(NodeState.ACTIVE)
        else:
            if self.state == NodeState.ACTIVE:
                log_state("yellow", "[CLUSTER]", f"[{self.node_id}] becoming STANDBY", 3)
                self.transition(NodeState.STANDBY)

    def _log_size(self):
        try:
            return len(load_events())
        except Exception:
            return 0

    def _file_size(self):
        try:
            return os.path.getsize("cluster/data/event_log.local.jsonl")
        except OSError:
            return 0

    def emit_heartbeat(self, peers):
        cluster_int = cluster_integrity_report()
        log_meta = {
            **get_last_append_meta(),
            "log_size": self._log_size(),
            "file_size": self._file_size(),
            "file_hash": file_sha256("cluster/data/event_log.local.jsonl"),
        }
        self.runtime_state.log_meta = log_meta
        self.runtime_state.cluster_integrity = cluster_int
        hb = {
            "node_id": self.node_id,
            "state": self.state.value,
            "priority": self.priority,
            "log_meta": log_meta,
            "cluster_integrity": {
                "integrity_ok": cluster_int.get("integrity_ok", False),
                "alive_nodes": cluster_int.get("alive_nodes", []),
                "per_peer": cluster_int.get("per_peer", {}),
            },
            "streams": self.runtime_state.active_streams,
        }
        for peer in peers:
            url = f"http://{peer['host']}:{peer['port']}/heartbeat"
            try:
                requests.post(url, json=hb, timeout=2)
            except requests.exceptions.RequestException:
                pass
