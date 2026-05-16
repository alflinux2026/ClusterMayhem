import time
import requests
from cluster.runtime.cluster_store import cluster_state
from cluster.runtime.registry import CLUSTER_REGISTRY
from cluster.runtime.leader import compute_leader

from cluster.utils.log_print import log_state

def forward_to_leader(event):

    leader = compute_leader()
    if not leader:

        log_state( "red", "NO LEADER", f"{event.event_id}", 3)

        return {"error": "no leader"}

    node = CLUSTER_REGISTRY[leader]
    url = f"http://{node['host']}:{node['port']}/route"

    # log_state( "cyan", "FORWARD", f"{event.event_id} -> leader {leader}", decimals=3 )

    requests.post(url, json=event.dict(), timeout=2)

    return {"forwarded_to": leader}


def forward_event(node_id, event):

    node = CLUSTER_REGISTRY[node_id]
    url = f"http://{node['host']}:{node['port']}/execute"

    log_state( "magenta", "WORKER SEND", f"{event.event_id} -> {node_id}", 3 )

    requests.post(url, json=event.dict(), timeout=2)


def route_event(event):

    alive = {
        node_id: data
        for node_id, data in cluster_state.items()
        if (time.time() - data["last_seen"]) < 3.0
    }

    if not alive:

        log_state( "red", "NO WORKERS", f"{event.event_id}", 3)

        return {"error": "no alive nodes"}

    log_state( "magenta", "ALIVE", f"{list(alive.keys())}", 3)

#    target = min(
    target = max(
        alive.items(),
        key=lambda x: (x[1]["priority"], x[0])
    )[0]

    log_state( "magenta", "WORKER", f"selected={target}", 3 )

    forward_event(target, event)

    return {"routed_to": target, "event_id": event.event_id}
