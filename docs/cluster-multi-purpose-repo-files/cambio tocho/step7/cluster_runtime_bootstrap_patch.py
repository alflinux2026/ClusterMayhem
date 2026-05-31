import json
import os
import socket
import requests
import hashlib

from cluster.runtime import context as ctx


def load_or_bootstrap_config():
    path = os.getenv("CLUSTER_CONFIG", "config/node.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    node_id = socket.gethostname()
    cfg = {
        "node_id": node_id,
        "priority": int(os.getenv("NODE_PRIORITY", "100")),
        "port": int(os.getenv("NODE_PORT", "8000")),
        "tenant_id": os.getenv("TENANT_ID", "default"),
        "app_id": os.getenv("APP_ID", "mayhem"),
        "data_type": os.getenv("DATA_TYPE", "event"),
        "schema_version": os.getenv("SCHEMA_VERSION", "0.1"),
        "peers": [],
    }
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return cfg
