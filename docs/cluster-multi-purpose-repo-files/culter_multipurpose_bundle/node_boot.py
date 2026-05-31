# File: cluster/runtime/node_boot.py
# Previous: none
# Author: alftorres
# Date: 2026-05-19T21:11:14+0200
# Version: 0.0.0
# Genealogy:
#   cluster/runtime/node_boot.py 0.0.0 2026-05-19T21:11:14+0200
#   God
#
# Purpose:
# Notes:
#
# FRV-ID: 500641938cf30f1e
# Header_End

"""
runtime.node_boot

Responsabilidad:
- Punto de entrada del proceso de nodo.
- Carga la configuración local, construye el runtime del nodo, inicializa
  el contexto global compartido, arranca el worker de fondo y expone la API HTTP.

Rol en la arquitectura:
- Este módulo actúa como ensamblador del nodo.
- No contiene lógica de negocio HTTP ni definición de endpoints.
- La lógica HTTP vive en runtime.api_app.
- La lógica periódica de cluster vive en runtime.node_worker.
"""

import threading
import uvicorn

from cluster.runtime.node_worker import NodeWorker
from cluster.runtime.node_runtime import NodeRuntime
from cluster.runtime.bootstrap import load_or_bootstrap_config
from cluster.runtime import context as ctx
from cluster.runtime.api_app import app
from cluster.utils.log_print import log_state


def run_node(config):
    ctx.node_id = config["node_id"]
    ctx.priority = config["priority"]

    node = NodeRuntime(node_id=config["node_id"], priority=config["priority"])
    ctx.node = node

    log_state("cyan", "[BOOT]", f"node={config['node_id']} priority={config['priority']} bind={config.get('bind_host', '0.0.0.0')}:{config.get('bind_port', 7000)} peers={len(config.get('peers', []))}", 3)

    worker = NodeWorker(node=node, peers=config["peers"], interval=1.0)
    threading.Thread(target=worker.start, daemon=True).start()

    log_state("green", "[WORKER]", f"background loop started for {config['node_id']}", 3)
    log_state("green", "[HTTP]", f"serving app on {config.get('bind_host', '0.0.0.0')}:{config.get('bind_port', 7000)}", 3)

    uvicorn.run(app, host=config.get("bind_host", "0.0.0.0"), port=config.get("bind_port", 7000), log_level="warning", access_log=False)


if __name__ == "__main__":
    config = load_or_bootstrap_config()
    run_node(config)
