import threading
import uvicorn

from cluster.runtime.node_worker import NodeWorker
from cluster.runtime.node_runtime import NodeRuntime
from cluster.runtime.bootstrap import load_or_bootstrap_config
from cluster.runtime import context as ctx
from cluster.runtime.api_app import app
from cluster.runtime.models import StreamKey
from cluster.utils.log_print import log_state


def build_stream_key(cfg) -> StreamKey:
    return StreamKey(
        tenant_id=str(cfg.get("tenant_id", "default")),
        app_id=str(cfg.get("app_id", "mayhem")),
        data_type=str(cfg.get("data_type", "event")),
        schema_version=str(cfg.get("schema_version", "0.1")),
    )


def main():
    cfg = load_or_bootstrap_config()
    ctx.stream = build_stream_key(cfg)
    ctx.node = NodeRuntime(cfg["node_id"], cfg["priority"])
    ctx.node_stream = ctx.stream
    ctx.nodeid = cfg["node_id"]
    ctx.node_id = cfg["node_id"]
    ctx.peers = cfg.get("peers", [])

    log_state("cyan", "[BOOT]", f"node={ctx.nodeid} stream={ctx.stream.stream_id()}", 3)

    worker = NodeWorker(ctx.node, ctx.peers)
    t = threading.Thread(target=worker.start, daemon=True)
    t.start()

    uvicorn.run(app, host="0.0.0.0", port=int(cfg["port"]))


if __name__ == "__main__":
    main()
