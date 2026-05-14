import json

def load_peers():
    with open("cluster/config/nodes.json") as f:
        data = json.load(f)

    return data["nodes"]
