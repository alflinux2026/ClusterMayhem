from pathlib import Path
out = Path('output')
out.mkdir(exist_ok=True)

log_replication = '''import logging
import time
import requests

from cluster.runtime import context as ctx
from cluster.runtime.cluster_store import cluster_state
from cluster.runtime.registry import CLUSTER_REGISTRY
from cluster.runtime.event_log import (
    get_local_log_path,
    load_replica_events,
    load_all_replica_events,
    load_cluster_events,
    list_replica_log_paths,
    load_events_from_path,
    get_last_append_meta,
)
from cluster.utils.log_print import log_state


def replicate_local():
    local_path = get_local_log_path()
    if not local_path:
        return
    for node_id, node in CLUSTER_REGISTRY.items():
        try:
            url = f"http://{node['host']}:{node['port']}/debug/log/replica/{ctx.node_id}"
            with open(local_path, 'r', encoding='utf-8') as f:
                content = f.read()
            requests.post(url, data=content.encode('utf-8'), timeout=2)
        except Exception as e:
            logging.debug(f"replicate_local failed for {node_id}: {e}")


def replicate_from_peer(node_id: str):
    node = CLUSTER_REGISTRY.get(node_id)
    if not node:
        return
    try:
        url = f"http://{node['host']}:{node['port']}/debug/log/replica/{ctx.node_id}"
        resp = requests.get(url, timeout=2)
        if resp.status_code == 200:
            return resp.text
    except Exception as e:
        logging.debug(f"replicate_from_peer failed for {node_id}: {e}")
    return None


def sync_replica_state():
    events = load_cluster_events()
    return {
        "replica_paths": list_replica_log_paths(),
        "replica_count": len(events),
        "last_append_meta": get_last_append_meta(),
    }
'''

state_machine = '''from cluster.runtime.events.event_state import EventStatus, validate_transition
from cluster.runtime.event_log import load_events, append_event
from cluster.runtime.events.cluster_event import ClusterEvent


def transition_event(event_id: str, new_status: EventStatus):
    events = load_events()
    latest = None
    for raw in reversed(events):
        if raw.get("event_id") == event_id:
            latest = raw
            break
    if not latest:
        return {"error": "event_not_found", "event_id": event_id}

    current_status = latest.get("status")
    if hasattr(current_status, "value"):
        current_status = current_status.value

    if not validate_transition(EventStatus(current_status), new_status):
        return {"error": "invalid_transition", "from": current_status, "to": new_status.value}

    updated = dict(latest)
    updated["status"] = new_status.value
    updated["updated_at"] = __import__('time').time()
    event = ClusterEvent(**updated)
    append_event(event)
    return {"ok": True, "event_id": event_id, "status": new_status.value}
'''

(out / 'cluster_runtime_log_replication_patch.py').write_text(log_replication, encoding='utf-8')
(out / 'cluster_runtime_state_machine_patch.py').write_text(state_machine, encoding='utf-8')
print('log_replication/state_machine patches ready')
