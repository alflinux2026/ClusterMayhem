# File: ./cluster/runtime/node_runtime.py
# Previous: none
# Author: alftorres
# Date: 2026-05-28T17:11:02+0200
# Version: 0.0.0
# Genealogy:
#   ./cluster/runtime/node_runtime.py 0.0.0 2026-05-28T17:11:02+0200
#   God
#
# Purpose:
#   Objeto principal que representa un nodo en el cluster.
#   NodeRuntime encapsula el estado, la identidad (node_id, priority) y el
#   comportamiento de un nodo: transiciones de estado, detección de líder,
#   y emisión de heartbeats a peers.
# Notes:
#   - Se instancia una vez por proceso (el nodo local)
#   - El estado se sincroniza con cluster_state mediante heartbeats
#   - ticker.tick() se llama en cada tick del worker (~1s) para detectar cambios de líder
#   - La transición STANDBY <-> ACTIVE es automática según quién sea el líder
#   - No hay persistencia de estado (se reinicia al arrancar)
#
# FRV-ID: 380b2fdaa1d41be7
# Header_End


import time
import requests

from cluster.runtime.state import NodeState, ensure_state_meta, transition_node_state
from cluster.runtime.leader import compute_leader
from cluster.utils.log_print import log_state


class NodeRuntime:
    """
    Representa un nodo en el cluster.

    Gestiona el estado del nodo, la detección automática de líder, y la
    emisión de heartbeats a otros nodos.

    Ciclo de vida típico:
        1. BOOT (inicialización)
        2. DISCOVERING (opcional, descubriendo peers)
        3. STANDBY (esperando a ser líder)
        4. ACTIVE (es el líder, procesa eventos)

    Si pierde el líder, vuelve a STANDBY. Si el nodo se vuelve líder,
    pasa a ACTIVE.

    Attributes:
        node_id (str): ID único del nodo.
        priority (int): Prioridad para leader election (menor = más prioritario).
        state (NodeState): Estado actual del nodo.
        last_heartbeat (float): Timestamp del último heartbeat enviado.
        state_since (float): Timestamp cuando se entró al estado actual.
        prev_state (str | None): Estado anterior.
        state_reason (str | None): Razón de la última transición.

    Example:
        >>> node = NodeRuntime("lnx203hp", priority=10)
        >>> node.node_id
        'lnx203hp'
        >>> node.priority
        10
        >>> node.state
        <NodeState.BOOT: 'BOOT'>

        >>> node.transition(NodeState.STANDBY, reason="boot_complete")
        {'changed': True, 'old_state': 'BOOT', 'new_state': 'STANDBY', ...}
    """

    def __init__(self, node_id, priority):
        """
        Inicializa un nodo del cluster.

        Args:
            node_id: ID único del nodo (string).
            priority: Prioridad para leader election (menor = más prioritario).

        Example:
            >>> node = NodeRuntime("lnx203hp", priority=10)
            >>> node = NodeRuntime("lnx200nas", priority=100)
        """
        self.node_id = node_id
        self.priority = priority
        self.state = NodeState.BOOT
        self.last_heartbeat = time.time()

        ensure_state_meta(self)
        self.state_reason = "node_init"

    def transition(self, new_state, reason=None):
        """
        Transiciona el nodo a un nuevo estado.

        Delega en transition_node_state() y muestra un log si el estado cambia.

        Args:
            new_state: Nuevo estado (NodeState enum o string).
            reason: Razón de la transición (ej: "leader_selected", "boot_complete").

        Returns:
            dict: Resultado de la transición (changed, old_state, new_state, ...).

        Example:
            >>> node.transition(NodeState.STANDBY, reason="boot_complete")
            [lnx203hp] BOOT -> STAND-BY (reason=boot_complete)
            {'changed': True, 'old_state': 'BOOT', 'new_state': 'STANDBY', ...}

            >>> node.transition(NodeState.ACTIVE, reason="leader_selected")
            [lnx203hp] STAND-BY -> ACTIVE (reason=leader_selected)
            {'changed': True, 'old_state': 'STANDBY', 'new_state': 'ACTIVE', ...}
        """
        result = transition_node_state(self, new_state, reason=reason)

        if result["changed"]:
            print(
                f"[{self.node_id}] "
                f"{result['old_state']} -> {result['new_state']} "
                f"(reason={result['state_reason']})"
            )

        return result

    def tick(self):
        """
        Ejecuta la lógica de cada tick del nodo (~1s).

        Comprueba quién es el líder y transiciona automáticamente:
            - Si soy el líder y estoy en STANDBY -> paso a ACTIVE
            - Si no soy el líder y estoy en ACTIVE -> paso a STANDBY

        Note:
            - Se llama en cada iteration del worker loop (~1s)
            - La transición es automática, no requiere comando externo
            - Si no hay líder (None), el nodo se queda en su estado actual

        Example:
            >>> node.state = NodeState.STANDBY
            >>> node.tick()  # Si soy líder
            [CLUSTER] [lnx203hp] becoming ACTIVE
            >>> node.state
            <NodeState.ACTIVE: 'ACTIVE'>
        """
        #        if self.state == NodeState.BOOT:
        #            self.transition(NodeState.STANDBY, reason="boot_complete")
        #            return

        #log_state("yellow", "[NodeRunTime tick]", f"[{self.node_id}] ticking ...", 3)

        leader = compute_leader()

        if leader == self.node_id:
            if self.state == NodeState.STANDBY:
                log_state("yellow", "[CLUSTER]", f"[{self.node_id}] becoming ACTIVE", 3)
                self.transition(NodeState.ACTIVE, reason="leader_selected")
        else:
            if self.state == NodeState.ACTIVE:
                log_state("yellow", "[CLUSTER]", f"[{self.node_id}] becoming STANDBY", 3)
                self.transition(NodeState.STANDBY, reason="leader_lost")

    def emit_heartbeat(self, peers):
        """
        Emite un heartbeat a todos los peers del cluster.

        Envía el estado actual del nodo (state, priority, state_since, ...)
        a todos los peers para que actualicen cluster_state.

        Args:
            peers: Lista de dicts con info de peers (cada uno tiene 'host' y 'port').

        Note:
            - Se usa POST /heartbeat en cada peer (api_app.py)
            - Timeout: 2s por peer
            - Falla silenciosamente si un peer no responde (no levanta exception)
            - Se llama en cada tick del worker (~1s)

        Example:
            >>> peers = [
            ...     {"host": "100.100.1.200", "port": 8000},
            ...     {"host": "100.100.1.201", "port": 8000}
            ... ]
            >>> node.emit_heartbeat(peers)
            # Envía POST http://100.100.1.200:8000/heartbeat y POST http://100.100.1.201:8000/heartbeat
        """
        hb = {
            "node_id": self.node_id,
            "state": self.state.value,
            "priority": self.priority,
            "state_since": getattr(self, "state_since", None),
            "prev_state": getattr(self, "prev_state", None),
            "state_reason": getattr(self, "state_reason", None),
        }

        for peer in peers:
            url = f"http://{peer['host']}:{peer['port']}/heartbeat"
            try:
                requests.post(url, json=hb, timeout=2)
            except requests.exceptions.RequestException:
                pass
