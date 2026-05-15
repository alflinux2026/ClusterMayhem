import requests
from cluster.runtime.leader import compute_leader
from cluster.runtime.cluster_store import cluster_state

def forward_to_leader(event):

    leader = compute_leader()
    if not leader:
        return {"error": "no leader"}

    node = cluster_state[leader]
    url = f"http://{node['host']}:{node['port']}/route"

    requests.post(url, json=event.dict(), timeout=2)

    return {"forwarded_to": leader}

def forward_event(node_id, event):

    node = cluster_state[node_id]
    url = f"http://{node['host']}:{node['port']}/execute"

    requests.post(url, json=event.dict(), timeout=2)

def route_event(event):

    alive = {
        node_id: data
        for node_id, data in cluster_state.items()
        if (time.time() - data["last_seen"]) < 3.0
    }

    target = min(
        alive.items(),
        key=lambda x: (x[1]["priority"], x[0])
    )[0]

    forward_event(target, event)

    return {"routed_to": target, "event_id": event.event_id}


