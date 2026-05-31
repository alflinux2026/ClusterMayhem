from typing import Any

node = None
node_id = None
nodeid = None
peers = []
stream = None
node_stream = None


def get_stream():
    return stream or node_stream
