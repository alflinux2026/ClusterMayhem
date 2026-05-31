CLUSTER_REGISTRY = {}


def register_node(node_id: str, host: str, port: int, priority: int = 100):
    CLUSTER_REGISTRY[node_id] = {
        "host": host,
        "port": port,
        "priority": priority,
    }
    return CLUSTER_REGISTRY[node_id]


def get_node(node_id: str):
    return CLUSTER_REGISTRY.get(node_id)
