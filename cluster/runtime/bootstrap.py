import socket
import json
import os
import requests
import hashlib


# -------------------------------------------------
# PRIORITY DETERMINISTIC (FIXA POR NODO)
# -------------------------------------------------
def deterministic_priority(node_id: str):
    return int(hashlib.md5(node_id.encode()).hexdigest(), 16) % 1000


# -------------------------------------------------
# BASIC UTILS
# -------------------------------------------------
def get_hostname():
    return socket.gethostname()


def load_config(path="config/node.local.json"):
    with open(path, "r") as f:
        return json.load(f)


# -------------------------------------------------
# DISCOVERY (MERGED VIEW SAFE)
# -------------------------------------------------
def discover_seed(peers):
    clusters = []

    for p in peers:
        try:
            r = requests.get(
                f"http://{p['host']}:{p['port']}/cluster",
                timeout=1
            )
            if r.status_code == 200:
                clusters.append(r.json())
        except:
            continue

    merged = {}

    for cluster in clusters:
        for node_id, data in cluster.items():

            if node_id not in merged:
                merged[node_id] = data
                continue

            # keep most recent info
            if data.get("last_seen", 0) > merged[node_id].get("last_seen", 0):
                merged[node_id] = data

    return merged


# -------------------------------------------------
# CONFIG GENERATION
# -------------------------------------------------
def generate_local_config(peers):
    hostname = get_hostname()

    priority = deterministic_priority(hostname)

    # resolve collisions deterministically (NO LOOP DRIFT)
    while priority in used_priorities:
        priority += 1000  # salt step to avoid clustering collisions

    config = {
        "node_id": hostname,
        "priority": priority,
        "bind_host": "0.0.0.0",
        "bind_port": 7000,
        "peers": peers
    }

    os.makedirs("config", exist_ok=True)

    with open("config/node.local.json", "w") as f:
        json.dump(config, f, indent=2)

    return config


# -------------------------------------------------
# BOOTSTRAP OR LOAD
# -------------------------------------------------
def load_or_bootstrap_config():
    try:
        return load_config()
    except FileNotFoundError:

        peers = [
            {"host": "100.100.1.200", "port": 7000},
            {"host": "100.100.1.202", "port": 7000},
            {"host": "100.100.1.203", "port": 7000},
        ]

        return generate_local_config(peers)
