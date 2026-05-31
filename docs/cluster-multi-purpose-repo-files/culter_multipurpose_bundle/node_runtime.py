import os
import time
import requests

from cluster.runtime.state import NodeState
from cluster.runtime.leader import compute_leader
from cluster.runtime.event_log import get_last_append_meta, load_events
from cluster.runtime.integrity import file_sha256, cluster_integrity_report

from cluster.utils.log_print import log_state


class NodeRuntime:
    def __init__(self, node_id, priority):
        self.node_id = node_id
        self.priority = priority
        self.state = NodeState.BOOT
        self.last_heartbeat = time.time()

    def transition(self, new_state):
        if self.state == new_state:
            return
        print(f"[{self.node_id}] {self.state} -> {new_state}")
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
        hb = {
            "node_id": self.node_id,
            "state": self.state.value,
            "priority": self.priority,
            "log_meta": {
                **get_last_append_meta(),
                "log_size": self._log_size(),
                "file_size": self._file_size(),
                "file_hash": file_sha256("cluster/data/event_log.local.jsonl"),
            },
            "cluster_integrity": {
                "integrity_ok": cluster_int.get("integrity_ok", False),
                "alive_nodes": cluster_int.get("alive_nodes", []),
                "per_peer": cluster_int.get("per_peer", {}),
            },
        }
        for peer in peers:
            url = f"http://{peer['host']}:{peer['port']}/heartbeat"
            try:
                requests.post(url, json=hb, timeout=2)
            except requests.exceptions.RequestException:
                pass
