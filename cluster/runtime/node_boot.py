# File: ./cluster/runtime/node_boot.py
# Previous: none
# Author: alftorres
# Date: 2026-05-28T17:10:49+0200
# Version: 0.0.0
# Genealogy:
#   ./cluster/runtime/node_boot.py 0.0.0 2026-05-28T17:10:49+0200
#   God
#
# Purpose:
#   Entry point del nodo del cluster.
#   Arranca el nodo: carga configuración, inicializa contexto global, crea NodeRuntime,
#   registra el nodo y peers en el registry, arranca el worker en background,
#   y sirve la API HTTP con uvicorn.
# Notes:
#   - Este es el archivo que se ejecuta con `python -m cluster.runtime.node_boot`
#   - La configuración viene de bootstrap.py (config.json o env vars)
#   - El worker se ejecuta en un hilo separado (daemon thread)
#   - uvicorn es el servidor HTTP que sirve api_app.py (FastAPI)
#   - El bloque __main__ permite ejecutar el script directamente o como módulo
#
# FRV-ID: 05bb09170fc30a8f
# Header_End

import uvicorn

from cluster.runtime.node_worker import NodeWorker
from cluster.runtime.node_runtime import NodeRuntime
from cluster.runtime.bootstrap import load_or_bootstrap_config
from cluster.runtime.registry import register_node
from cluster.runtime.event_log import ensure_initial_files
from cluster.runtime import context as ctx
from cluster.runtime.api_app import app
from cluster.utils.log_print import log_state


def run_node(config):
    """
    Arranca un nodo del cluster.

    Secuencia de inicialización:
        1. Crea archivos iniciales de event log (si no existen)
        2. Inicializa contexto global (ctx.node_id, ctx.node, ctx.peers, ...)
        3. Crea NodeRuntime (nodo local, estado BOOT)
        4. Registra nodo local y peers en CLUSTER_REGISTRY
        5. Arranca NodeWorker en hilo background
        6. Arranca uvicorn (servidor HTTP)

    Args:
        config (dict): Configuración del nodo con:
            - node_id (str): ID único del nodo
            - priority (int): Prioridad para leader election
            - host (str): Hostname/IP del nodo
            - port (int): Puerto del nodo
            - bind_host (str): Host para bind del servidor HTTP (default: 0.0.0.0)
            - bind_port (int): Puerto para bind del servidor HTTP (default: 7000)
            - peers (list[dict]): Lista de peers con node_id, host, port, priority

    Example:
        >>> config = {
        ...     "node_id": "lnx203hp",
        ...     "priority": 10,
        ...     "host": "100.100.1.200",
        ...     "port": 8000,
        ...     "bind_host": "0.0.0.0",
        ...     "bind_port": 7000,
        ...     "peers": [
        ...         {"node_id": "lnx200nas", "host": "100.100.1.201", "port": 8000, "priority": 100}
        ...     ]
        ... }
        >>> run_node(config)
        # Arranca el nodo lnx203hp con peer lnx200nas
    """
    ensure_initial_files()

    ctx.node_id = config["node_id"]
    ctx.nodeid = config["node_id"]
    ctx.priority = config["priority"]
    ctx.peers = config.get("peers", [])

    node = NodeRuntime(
        node_id=config["node_id"],
        priority=config["priority"],
    )
    ctx.node = node

    register_node(
        node_id=config["node_id"],
        host=config["host"],
        port=config["port"],
        priority=config["priority"],
    )

    for peer in config.get("peers", []):
        register_node(
            node_id=peer["node_id"],
            host=peer["host"],
            port=peer["port"],
            priority=peer["priority"],
        )

    log_state(
        "cyan",
        "[BOOT]",
        (
            f"node={config['node_id']} "
            f"priority={config['priority']} "
            f"bind={config.get('bind_host', '0.0.0.0')}:{config.get('bind_port', 7000)} "
            f"peers={len(config.get('peers', []))} "
            f"state={node.state.value} "
            f"state_since={getattr(node, 'state_since', None)} "
            f"reason={getattr(node, 'state_reason', None)}"
        ),
        3,
    )

    worker = NodeWorker(
        node=node,
        peers=config["peers"],
        interval=1.0,
    )
    worker.start()

    log_state("green", "[WORKER]", f"background loop started for {config['node_id']}", 3)
    log_state(
        "green",
        "[HTTP]",
        f"serving app on {config.get('bind_host', '0.0.0.0')}:{config.get('bind_port', 7000)}",
        3,
    )

    uvicorn.run(
        app,
        host=config.get("bind_host", "0.0.0.0"),
        port=config.get("bind_port", 7000),
        log_level="warning",
        access_log=False,
    )


if __name__ == "__main__":
    """
    Entry point cuando se ejecuta el script directamente.

    Carga la configuración (de config.json o env vars) y arranca el nodo.

    Example:
        # Ejecutar como script
        $ python cluster/runtime/node_boot.py

        # Ejecutar como módulo
        $ python -m cluster.runtime.node_boot
    """
    config = load_or_bootstrap_config()
    run_node(config)
