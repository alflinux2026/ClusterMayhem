# File: ./cluster/utils/chaos/chaos_torture.py
# Previous: none
# Author: alftorres
# Date: 2026-05-28T17:XX:XX+0200
# Version: 0.0.0
# Genealogy:
#   ./cluster/utils/chaos/chaos_torture.py 0.0.0 2026-05-28T17:XX:XX+0200
#   God
#
# Purpose:
#   Chaos testing / torture test para el cluster.
#   Envía eventos concurrentes a múltiples nodos mientras mata/revive nodos
#   aleatoriamente (sleep/revive) para probar resiliencia, tolerancia a fallos,
#   y recovery del cluster. Mide latencia, success rate, y genera stats detalladas.
# Notes:
#   - 3 modos: smoke (100 eventos, sin chaos), benchmark (5000 eventos, 5% kill), torture (100k eventos, 5% kill)
#   - Kill probability: 5% de probabilidad de matar un nodo por evento
#   - Death time: 1.5s - 15s (nodo dormido antes de revivir)
#   - Retry con backoff exponencial: base=0.5s, max=3.0s, max_retries=25
#   - Send workers: 4 hilos concurrentes enviando eventos
#   - Output: stats.json (resumen) + events.csv (detalle por evento)
#   - Stats: success_rate, latency (avg, min, p50, p95, p99, max), per_node ok/fail, leaders_seen
#   - Al final revive TODOS los nodos para restaurar el cluster
#
# FRV-ID: xxxx
# Header_End

import time
import json
import random
import requests
import threading
import uuid
import argparse
import queue
import csv
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict
from pathlib import Path

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.models import StreamKey

# =============================================================================
# Configuración por defecto
# =============================================================================

#: Nodos por defecto del cluster
DEFAULT_NODES = ["http://100.100.1.200:7000", "http://100.100.1.202:7000", "http://100.100.1.203:7000"]

#: Número de eventos por defecto
DEFAULT_EVENTS = 100000

#: Delay mínimo entre eventos (segundos)
DEFAULT_EVENT_DELAY_MIN = 0.1

#: Delay máximo entre eventos (segundos)
DEFAULT_EVENT_DELAY_MAX = 0.2

#: Probabilidad de matar un nodo por evento (5%)
DEFAULT_KILL_PROBABILITY = 0.05

#: Tiempo mínimo de muerte (nodo dormido) en segundos
DEFAULT_DEATH_TIME_MIN = 1.5

#: Tiempo máximo de muerte (nodo dormido) en segundos
DEFAULT_DEATH_TIME_MAX = 15.0

#: Timeout de request en segundos
DEFAULT_REQUEST_TIMEOUT = 5.0

#: Máximo número de retries por evento
DEFAULT_MAX_RETRIES = 25

#: Umbral de evento lento en milisegundos
DEFAULT_SLOW_EVENT_THRESHOLD_MS = 500.0

#: Nodo a dormir solo (si None, se elige aleatorio)
DEFAULT_SLEEP_ONLY_NODE = None

#: Número de workers enviando eventos
DEFAULT_SEND_WORKERS = 4

#: Base para backoff exponencial de retry
DEFAULT_RETRY_BACKOFF_BASE = 0.5

#: Máximo backoff de retry en segundos
DEFAULT_RETRY_BACKOFF_MAX = 3.0

#: Tenant ID por defecto
DEFAULT_TENANT_ID = "chaos"

#: App ID por defecto
DEFAULT_APP_ID = "chaos_v4"

#: Data type por defecto
DEFAULT_DATA_TYPE = "event"

#: Schema version por defecto
DEFAULT_SCHEMA_VERSION = "0.1"


def parse_args():
    """
    Parsea argumentos de línea de comando.

    Returns:
        argparse.Namespace: Argumentos parseados.

    Example:
        # Smoke test
        $ python chaos_torture.py --mode smoke

        # Benchmark
        $ python chaos_torture.py --mode benchmark --events 10000

        # Torture
        $ python chaos_torture.py --mode torture --nodes http://10.0.0.1:7000 http://10.0.0.2:7000
    """
    p = argparse.ArgumentParser(description="Universal chaos torture runner final v2")
    p.add_argument("--mode", choices=["smoke", "benchmark", "torture"], default="benchmark")
    p.add_argument("--nodes", nargs="+", default=DEFAULT_NODES)
    p.add_argument("--events", type=int, default=DEFAULT_EVENTS)
    p.add_argument("--delay-min", type=float, default=DEFAULT_EVENT_DELAY_MIN)
    p.add_argument("--delay-max", type=float, default=DEFAULT_EVENT_DELAY_MAX)
    p.add_argument("--kill-prob", type=float, default=DEFAULT_KILL_PROBABILITY)
    p.add_argument("--death-min", type=float, default=DEFAULT_DEATH_TIME_MIN)
    p.add_argument("--death-max", type=float, default=DEFAULT_DEATH_TIME_MAX)
    p.add_argument("--timeout", type=float, default=DEFAULT_REQUEST_TIMEOUT)
    p.add_argument("--retries", type=int, default=DEFAULT_MAX_RETRIES)
    p.add_argument("--sleep-only-node", default=DEFAULT_SLEEP_ONLY_NODE)
    p.add_argument("--slow-ms", type=float, default=DEFAULT_SLOW_EVENT_THRESHOLD_MS)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--output", default=None)
    p.add_argument("--send-workers", type=int, default=DEFAULT_SEND_WORKERS)
    p.add_argument("--retry-backoff-base", type=float, default=DEFAULT_RETRY_BACKOFF_BASE)
    p.add_argument("--retry-backoff-max", type=float, default=DEFAULT_RETRY_BACKOFF_MAX)
    p.add_argument("--drain-timeout", type=float, default=60.0)
    p.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    p.add_argument("--app-id", default=DEFAULT_APP_ID)
    p.add_argument("--data-type", default=DEFAULT_DATA_TYPE)
    p.add_argument("--schema-version", default=DEFAULT_SCHEMA_VERSION)
    return p.parse_args()


ARGS = parse_args()
if ARGS.seed is not None:
    random.seed(ARGS.seed)

# Presets de configuración por modo
MODE_PRESETS = {
    "smoke": {"events": 100, "kill_prob": 0.0, "delay_min": 0.1, "delay_max": 0.2, "retries": 3, "send_workers": 2, "drain_timeout": 15.0},
    "benchmark": {"events": 5000, "kill_prob": 0.05, "delay_min": 0.1, "delay_max": 0.2, "retries": 10, "send_workers": 4, "drain_timeout": 30.0},
    "torture": {"events": 100000, "kill_prob": 0.05, "delay_min": 0.1, "delay_max": 0.2, "retries": 25, "send_workers": 4, "drain_timeout": 60.0},
}

preset = MODE_PRESETS[ARGS.mode]
NODES = ARGS.nodes
EVENTS = ARGS.events if ARGS.events != DEFAULT_EVENTS else preset["events"]
EVENT_DELAY_RANGE = (ARGS.delay_min, ARGS.delay_max) if (ARGS.delay_min, ARGS.delay_max) != (DEFAULT_EVENT_DELAY_MIN, DEFAULT_EVENT_DELAY_MAX) else (preset["delay_min"], preset["delay_max"])
KILL_PROBABILITY = ARGS.kill_prob if ARGS.kill_prob != DEFAULT_KILL_PROBABILITY else preset["kill_prob"]
DEATH_TIME_RANGE = (ARGS.death_min, ARGS.death_max)
REQUEST_TIMEOUT = ARGS.timeout
MAX_RETRIES = ARGS.retries if ARGS.retries != DEFAULT_MAX_RETRIES else preset["retries"]
SLEEP_ONLY_NODE = ARGS.sleep_only_node
SLOW_EVENT_THRESHOLD_MS = ARGS.slow_ms
SEND_WORKERS = ARGS.send_workers if ARGS.send_workers != DEFAULT_SEND_WORKERS else preset["send_workers"]
RETRY_BACKOFF_BASE = ARGS.retry_backoff_base
RETRY_BACKOFF_MAX = ARGS.retry_backoff_max
DRAIN_TIMEOUT = ARGS.drain_timeout if ARGS.drain_timeout != 60.0 else preset["drain_timeout"]
STREAM_KEY = StreamKey(tenant_id=ARGS.tenant_id, app_id=ARGS.app_id, data_type=ARGS.data_type, schema_version=ARGS.schema_version)

TEST_STARTED_AT = time.time()
RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S")


CHAOS_BASE_DIR = ( ROOT / "utils" / "chaos" )
CHAOS_BASE_DIR.mkdir( parents=True, exist_ok=True )
OUT_DIR = ( Path(ARGS.output) if ARGS.output else CHAOS_BASE_DIR / f"chaos_out_{RUN_ID}" )

OUT_DIR.mkdir(parents=True, exist_ok=True)
STATS_FILE = OUT_DIR / "stats.json"
EVENTS_CSV = OUT_DIR / "events.csv"

TEST_CONFIG = {
    "mode": ARGS.mode,
    "nodes": NODES,
    "events": EVENTS,
    "event_delay_range": EVENT_DELAY_RANGE,
    "kill_probability": KILL_PROBABILITY,
    "death_time_range": DEATH_TIME_RANGE,
    "request_timeout": REQUEST_TIMEOUT,
    "max_retries": MAX_RETRIES,
    "sleep_only_node": SLEEP_ONLY_NODE,
    "slow_event_threshold_ms": SLOW_EVENT_THRESHOLD_MS,
    "seed": ARGS.seed,
    "run_id": RUN_ID,
    "stats_file": str(STATS_FILE),
    "events_csv": str(EVENTS_CSV),
    "send_workers": SEND_WORKERS,
    "retry_backoff_base": RETRY_BACKOFF_BASE,
    "retry_backoff_max": RETRY_BACKOFF_MAX,
    "drain_timeout": DRAIN_TIMEOUT,
    "stream": {"tenant_id": STREAM_KEY.tenant_id, "app_id": STREAM_KEY.app_id, "data_type": STREAM_KEY.data_type, "schema_version": STREAM_KEY.schema_version, "stream_id": STREAM_KEY.stream_id()},
}

# =============================================================================
# Variables globales de estado
# =============================================================================

kill_threads = []
dead_nodes = set()
dead_lock = threading.Lock()
stats_lock = threading.Lock()
producer_done_lock = threading.Lock()
enqueue_seq_lock = threading.Lock()
pending_queue = queue.PriorityQueue()
producer_done = False
enqueue_seq = 0
worker_sessions = {}
worker_sessions_lock = threading.Lock()
results_lock = threading.Lock()
results = []
stats = {"events_total": 0, "events_ok": 0, "events_failed": 0, "events_retried": 0, "events_no_leader": 0, "events_timeout": 0, "events_connection_error": 0, "events_forward_error": 0, "events_unexpected_fail": 0, "events_slow": 0, "kills": 0, "revives": 0, "kill_attempts": 0, "kill_failures": 0, "revive_failures": 0, "per_node_ok": defaultdict(int), "per_node_fail": defaultdict(int), "leaders_seen": defaultdict(int), "latency": [], "unexpected_failures": [], "slow_events": [], "kill_events": [], "submit_http_200": 0, "submit_semantic_ok": 0, "submit_hard_fail": 0, "queue_requeues": 0, "queue_max_depth": 0}


@dataclass
class PendingEvent:
    """
    Evento pendiente de enviar (con retry).

    Attributes:
        event_index: Índice del evento (0, 1, 2, ...).
        event (dict): Datos del evento.
        retries_done (int): Número de retries ya hechos.
        tried_nodes (set): Nodos ya intentados para este evento.
        first_enqueued_at (float): Timestamp cuando se encoló por primera vez.
    """
    event_index: int
    event: dict
    retries_done: int = 0
    tried_nodes: set = field(default_factory=set)
    first_enqueued_at: float = field(default_factory=time.time)


def build_event(i):
    """
    Construye un evento de chaos test.

    Args:
        i: Índice del evento.

    Returns:
        dict: Evento con event_id, trace_id, payload, stream, etc.
    """
    return {"event_id": str(uuid.uuid4()), "trace_id": str(uuid.uuid4()), "event_type": "chaos.test", "payload": {"msg": f"msg-203: {i}", "seq": i, "source": "chaos_203", "run_id": RUN_ID, "stream_id": STREAM_KEY.stream_id()}, "stream": {"tenant_id": STREAM_KEY.tenant_id, "app_id": STREAM_KEY.app_id, "data_type": STREAM_KEY.data_type, "schema_version": STREAM_KEY.schema_version, "stream_id": STREAM_KEY.stream_id()}, "stream_id": STREAM_KEY.stream_id(), "tenant_id": STREAM_KEY.tenant_id, "app_id": STREAM_KEY.app_id, "data_type": STREAM_KEY.data_type, "schema_version": STREAM_KEY.schema_version, "status": "created", "route_hops": [], "source_node": None, "target_node": None, "execution_key": None, "created_at": time.time(), "updated_at": time.time(), "received_at": None, "attempt": 0}


def stat_inc(key, amount=1):
    """Incrementa un contador de stats."""
    with stats_lock:
        stats[key] += amount


def stat_node_ok(node):
    """Contabiliza un evento OK para un nodo."""
    with stats_lock:
        stats["per_node_ok"][node] += 1


def stat_node_fail(node):
    """Contabiliza un evento FAIL para un nodo."""
    with stats_lock:
        stats["per_node_fail"][node] += 1


def stat_leader(name):
    """Contabiliza un líder visto."""
    with stats_lock:
        stats["leaders_seen"][name] += 1


def stat_latency(ms):
    """Registra una latencia."""
    with stats_lock:
        stats["latency"].append(ms)


def stat_unexpected_failure(event_index, attempt, node, status_code=None, payload=None, reason=None):
    """Registra un fallo inesperado."""
    with stats_lock:
        stats["events_unexpected_fail"] += 1
        stats["unexpected_failures"].append({"event_index": event_index, "attempt": attempt, "node": node, "status_code": status_code, "payload": payload, "reason": reason, "timestamp": datetime.now().isoformat()})


def stat_slow_event(event_index, attempt, node, latency_ms, leader=None, payload=None):
    """Registra un evento lento."""
    with stats_lock:
        stats["events_slow"] += 1
        stats["slow_events"].append({"event_index": event_index, "attempt": attempt, "node": node, "latency_ms": round(latency_ms, 3), "leader": leader, "payload": payload, "timestamp": datetime.now().isoformat()})


def stat_kill_event(node, action, ok, payload=None, error=None, seconds=None):
    """Registra un evento de kill/revive."""
    with stats_lock:
        stats["kill_events"].append({"action": action, "node": node, "ok": ok, "seconds": seconds, "payload": payload, "error": error, "timestamp": datetime.now().isoformat()})


def percentile(data, p):
    """
    Calcula el percentil p de una lista de datos.

    Args:
        data: Lista de valores numéricos.
        p: Percentil a calcular (0-100).

    Returns:
        float: Percentil p (interpolación lineal).
    """
    if not data:
        return 0.0
    values = sorted(data)
    if len(values) == 1:
        return float(values[0])
    rank = (len(values) - 1) * (p / 100.0)
    low = int(rank)
    high = min(low + 1, len(values) - 1)
    return float(values[low] + (values[high] - values[low]) * (rank - low))


def is_retryable_response(payload):
    """
    Comprueba si una respuesta es retryable.

    Args:
        payload: Dict de respuesta.

    Returns:
        bool: True si es retryable (no leader, isolated, timeout, connection, etc.).
    """
    if not isinstance(payload, dict):
        return False
    if payload.get("error") in {"no leader", "node isolated"}:
        return True
    return any(p in str(payload.get("error", "")).lower() for p in ["timeout", "connection", "refused", "temporarily unavailable", "isolated", "no leader"])


def extract_leader(payload):
    """Extrae el node_id del líder de una respuesta."""
    if not isinstance(payload, dict):
        return None
    if "result" in payload and isinstance(payload["result"], dict):
        return payload["result"].get("leader")
    return payload.get("leader")


def classify_submit_response(status_code, payload):
    """
    Clasifica la respuesta de un submit de evento.

    Args:
        status_code: Código HTTP de la respuesta.
        payload: Dict de respuesta.

    Returns:
        str: "submit_ok", "retryable_error", "hard_fail", o "http_not_ok".
    """
    if status_code != 200:
        return "http_not_ok"
    if not isinstance(payload, dict):
        return "submit_ok"
    if payload.get("error"):
        return "retryable_error" if is_retryable_response(payload) else "hard_fail"
    result = payload.get("result")
    if isinstance(result, dict) and result.get("error"):
        return "retryable_error" if is_retryable_response(result) else "hard_fail"
    return "submit_ok"


def next_enqueue_seq():
    """Genera el siguiente número de secuencia de encolado (thread-safe)."""
    global enqueue_seq
    with enqueue_seq_lock:
        enqueue_seq += 1
        return enqueue_seq


def enqueue_pending(pending, delay_seconds=0.0):
    """
    Encola un evento pendiente para enviar.

    Args:
        pending: PendingEvent a encolar.
        delay_seconds: Segundos de delay antes de intentar enviar.
    """
    run_at = time.time() + max(0.0, delay_seconds)
    pending_queue.put((run_at, next_enqueue_seq(), pending))
    with stats_lock:
        stats["queue_max_depth"] = max(stats["queue_max_depth"], pending_queue.qsize())


def mark_producer_done():
    """Marca que el producer ha terminado de generar eventos."""
    global producer_done
    with producer_done_lock:
        producer_done = True


def is_producer_done():
    """Comprueba si el producer ha terminado."""
    with producer_done_lock:
        return producer_done


def compute_retry_backoff(retries_done):
    """
    Calcula el backoff para retry (exponencial).

    Args:
        retries_done: Número de retries ya hechos.

    Returns:
        float: Backoff en segundos (base * 2^(retries_done - 1), max RETRY_BACKOFF_MAX).
    """
    return min(RETRY_BACKOFF_BASE * (2 ** max(0, retries_done - 1)), RETRY_BACKOFF_MAX)


def print_test_config():
    """Imprime la configuración del test."""
    print("\\n" + "=" * 56)
    print(f"CHAOS TEST CONFIG [{ARGS.mode}]")
    print("=" * 56)
    for k, v in TEST_CONFIG.items():
        if k == "stream":
            print(f"{k}: {v['stream_id']}")
        else:
            print(f"{k}: {v}")
    print("=" * 56 + "\n")


def get_session(worker_id):
    """
    Obtiene o crea una sesión requests para un worker.

    Args:
        worker_id: ID del worker.

    Returns:
        requests.Session: Sesión con connection pooling.
    """
    with worker_sessions_lock:
        if worker_id not in worker_sessions:
            s = requests.Session()
            adapter = requests.adapters.HTTPAdapter(pool_connections=16, pool_maxsize=16, max_retries=0)
            s.mount("http://", adapter)
            s.mount("https://", adapter)
            worker_sessions[worker_id] = s
        return worker_sessions[worker_id]


def kill_node(node, seconds=None):
    """
    Mata un nodo (sleep).

    Args:
        node: URL del nodo.
        seconds: Segundos que durará muerto (para logging).

    Returns:
        bool: True si se mató exitosamente, False si falló.
    """
    stat_inc("kill_attempts")
    try:
        resp = requests.post(f"{node}/sleep", timeout=2)
        try:
            payload = resp.json()
        except Exception:
            payload = {"raw_text": resp.text}
        if resp.status_code == 200 and payload.get("ok") is True:
            with dead_lock:
                dead_nodes.add(node)
            stat_inc("kills")
            stat_kill_event(node=node, action="sleep", ok=True, payload=payload, seconds=seconds)
            print(f"[CHAOS] SLEEP {node}")
            return True
        stat_inc("kill_failures")
        stat_kill_event(node=node, action="sleep", ok=False, payload=payload, seconds=seconds)
        print(f"[CHAOS FAIL SLEEP] {node} -> status={resp.status_code} payload={payload}")
        return False
    except Exception as e:
        stat_inc("kill_failures")
        stat_kill_event(node=node, action="sleep", ok=False, error=str(e), seconds=seconds)
        print(f"[CHAOS FAIL SLEEP] {node} -> {e}")
        return False


def revive_node(node):
    """
    Revive un nodo (revive).

    Args:
        node: URL del nodo.

    Returns:
        bool: True si se revivió exitosamente, False si falló.
    """
    try:
        resp = requests.post(f"{node}/revive", timeout=2)
        try:
            payload = resp.json()
        except Exception:
            payload = {"raw_text": resp.text}
        if resp.status_code == 200 and payload.get("ok") is True:
            with dead_lock:
                dead_nodes.discard(node)
            stat_inc("revives")
            stat_kill_event(node=node, action="revive", ok=True, payload=payload)
            print(f"[CHAOS] REVIVE {node}")
            return True
        stat_inc("revive_failures")
        stat_kill_event(node=node, action="revive", ok=False, payload=payload)
        print(f"[CHAOS FAIL REVIVE] {node} -> status={resp.status_code} payload={payload}")
        return False
    except Exception as e:
        stat_inc("revive_failures")
        stat_kill_event(node=node, action="revive", ok=False, error=str(e))
        print(f"[CHAOS FAIL REVIVE] {node} -> {e}")
        return False


def kill_cycle(node, seconds):
    """
    Ciclo de kill: mata el nodo, espera seconds, y lo revive.

    Args:
        node: URL del nodo.
        seconds: Segundos que durará muerto.
    """
    try:
        if kill_node(node, seconds=seconds):
            print(f"[CHAOS] DEAD {node} for {seconds:.2f}s")
            time.sleep(seconds)
    finally:
        revive_node(node)


def process_pending_event(pending: PendingEvent, worker_id: int):
    """
    Procesa un evento pendiente (envía, retry si falla).

    Args:
        pending: Evento pendiente.
        worker_id: ID del worker.

    Returns:
        bool: True si el evento se envió exitosamente, False si falló definitivamente.
    """
    i = pending.event_index
    event = pending.event
    attempt_number = pending.retries_done + 1
    available = [n for n in NODES if n not in pending.tried_nodes]
    if not available:
        pending.tried_nodes.clear()
        available = list(NODES)
    node = random.choice(available)
    pending.tried_nodes.add(node)
    start = time.time()
    session = get_session(worker_id)
    try:
        r = session.post(f"{node}/event", json=event, timeout=REQUEST_TIMEOUT)
        elapsed_ms = (time.time() - start) * 1000
        stat_latency(elapsed_ms)
        try:
            payload = r.json()
        except Exception:
            payload = {"raw_text": r.text}
        leader = extract_leader(payload)
        if leader:
            stat_leader(leader)
        if elapsed_ms >= SLOW_EVENT_THRESHOLD_MS:
            stat_slow_event(i, attempt_number, node, elapsed_ms, leader, payload)
        if r.status_code == 200:
            stat_inc("submit_http_200")
        result = classify_submit_response(r.status_code, payload)
        row = {"event_index": i, "attempt": attempt_number, "node": node, "status_code": r.status_code, "elapsed_ms": round(elapsed_ms, 3), "leader": leader, "result": result, "final": None}
        if result == "submit_ok":
            stat_inc("events_ok")
            stat_inc("submit_semantic_ok")
            stat_node_ok(node)
            row["final"] = "ok"
            with results_lock:
                results.append(row)
            print(f"[TORTURE] {i:03} OK attempt={attempt_number} node={node} leader={leader} latency={elapsed_ms:.1f}ms")
            return True
        if result == "retryable_error" or r.status_code >= 500:
            stat_inc("events_retried")
            if isinstance(payload, dict) and payload.get("error") == "no leader":
                stat_inc("events_no_leader")
            result_payload = payload.get("result") if isinstance(payload.get("result"), dict) else None
            if isinstance(result_payload, dict) and result_payload.get("error") == "no leader":
                stat_inc("events_no_leader")
            row["final"] = "retry"
            with results_lock:
                results.append(row)
            print(f"[RETRY] {i:03} attempt={attempt_number} node={node} status={r.status_code} payload={payload}")
            if pending.retries_done + 1 >= MAX_RETRIES:
                stat_inc("events_failed")
                stat_unexpected_failure(i, attempt_number, node, r.status_code, payload, "dropped_after_retries_retryable_response")
                print(f"[DROP] {i:03} event dropped after retries")
                return False
            pending.retries_done += 1
            stat_inc("queue_requeues")
            enqueue_pending(pending, compute_retry_backoff(pending.retries_done))
            return False
        stat_inc("events_failed")
        stat_inc("submit_hard_fail")
        stat_node_fail(node)
        stat_unexpected_failure(i, attempt_number, node, r.status_code, payload, "hard_fail_non_retryable_response")
        row["final"] = "hard_fail"
        with results_lock:
            results.append(row)
        print(f"[FAIL] {i:03} attempt={attempt_number} node={node} status={r.status_code} payload={payload}")
        return False
    except requests.Timeout as e:
        stat_inc("events_timeout")
        stat_inc("events_retried")
        print(f"[TIMEOUT] {i:03} attempt={attempt_number} {node} -> {e}")
    except requests.ConnectionError as e:
        stat_inc("events_connection_error")
        stat_inc("events_retried")
        print(f"[CONNECTION] {i:03} attempt={attempt_number} {node} -> {e}")
    except Exception as e:
        stat_inc("events_forward_error")
        stat_inc("events_retried")
        stat_unexpected_failure(i, attempt_number, node, reason=f"exception:{type(e).__name__}", payload={"exception": str(e)})
        print(f"[ERROR] {i:03} attempt={attempt_number} {node} -> {e}")
    if pending.retries_done + 1 >= MAX_RETRIES:
        stat_inc("events_failed")
        stat_unexpected_failure(i, attempt_number, node, reason="dropped_after_retries_exception", payload={"tried_nodes": list(pending.tried_nodes)})
        print(f"[DROP] {i:03} event dropped after retries")
        return False
    pending.retries_done += 1
    stat_inc("queue_requeues")
    enqueue_pending(pending, compute_retry_backoff(pending.retries_done))
    return False


def sender_worker(worker_id):
    """
    Worker que envía eventos desde la cola.

    Args:
        worker_id: ID del worker.

    Note:
        - Se ejecuta en un hilo daemon
        - Saca eventos de pending_queue y los procesa
        - Termina cuando producer_done=True y la cola está vacía
    """
    while True:
        try:
            run_at, _, pending = pending_queue.get(timeout=0.5)
        except queue.Empty:
            if is_producer_done() and pending_queue.empty():
                return
            continue
        now = time.time()
        if run_at > now:
            pending_queue.put((run_at, next_enqueue_seq(), pending))
            pending_queue.task_done()
            time.sleep(min(run_at - now, 0.2))
            continue
        try:
            process_pending_event(pending, worker_id)
        finally:
            pending_queue.task_done()


def chaos_loop():
    """
    Loop principal del chaos test.

    Genera EVENTS eventos, y con probabilidad KILL_PROBABILITY
    mata un nodo aleatorio por seconds aleatorios.
    """
    for i in range(EVENTS):
        if random.random() < KILL_PROBABILITY:
            node = SLEEP_ONLY_NODE if SLEEP_ONLY_NODE else random.choice(NODES)
            seconds = random.uniform(*DEATH_TIME_RANGE)
            t = threading.Thread(target=kill_cycle, args=(node, seconds), daemon=True)
            t.start()
            kill_threads.append(t)
        stat_inc("events_total")
        enqueue_pending(PendingEvent(event_index=i, event=build_event(i)), delay_seconds=0.0)
        time.sleep(random.uniform(*EVENT_DELAY_RANGE))
    mark_producer_done()


def revive_everything():
    """
    Revive TODOS los nodos (force revive).

    Se llama al final del test para restaurar el cluster.
    """
    print("\\n[MAIN] REVIVING ALL NODES\\n")
    for node in sorted(set(NODES)):
        try:
            requests.post(f"{node}/revive", timeout=2)
            print(f"[FORCE REVIVE] {node}")
        except Exception as e:
            print(f"[FORCE REVIVE FAIL] {node} -> {e}")


def wait_kills():
    """Espera a que terminen todos los kill threads."""
    print("\\n[MAIN] waiting active kill cycles...\\n")
    for t in kill_threads:
        t.join(timeout=30)


def wait_queue_drain():
    """
    Espera a que la cola se vacíe (drain).

    Returns:
        bool: True si la cola se vació, False si timeout.
    """
    deadline = time.time() + DRAIN_TIMEOUT
    while time.time() < deadline:
        if pending_queue.empty():
            time.sleep(0.5)
            if pending_queue.empty():
                return True
        time.sleep(0.2)
    return False


def write_csv_and_json():
    """
    Escribe stats.json y events.csv.

    Calcula success_rate, latencia (avg, min, p50, p95, p99, max),
    y guarda todo el report.
    """
    with results_lock:
        rows = list(results)
    with open(EVENTS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["event_index", "attempt", "node", "status_code", "elapsed_ms", "leader", "result", "final"])
        writer.writeheader()
        writer.writerows(rows)
    with stats_lock:
        total = stats["events_total"]
        ok = stats["events_ok"]
        failed = stats["events_failed"]
        success_rate = ((ok / total) * 100) if total else 0
        avg_latency = (sum(stats["latency"]) / len(stats["latency"])) if stats["latency"] else 0
        max_latency = max(stats["latency"]) if stats["latency"] else 0
        min_latency = min(stats["latency"]) if stats["latency"] else 0
        p50_latency = percentile(stats["latency"], 50)
        p95_latency = percentile(stats["latency"], 95)
        p99_latency = percentile(stats["latency"], 99)
        report = {"test_config": TEST_CONFIG, "run_meta": {"started_at_epoch": TEST_STARTED_AT, "ended_at_epoch": time.time(), "started_at_iso": datetime.fromtimestamp(TEST_STARTED_AT).isoformat(), "ended_at_iso": datetime.now().isoformat(), "duration_seconds": round(time.time() - TEST_STARTED_AT, 3)}, "stats": {**stats, "success_rate": round(success_rate, 2), "latency_avg": round(avg_latency, 3), "latency_min": round(min_latency, 3), "latency_p50": round(p50_latency, 3), "latency_p95": round(p95_latency, 3), "latency_p99": round(p99_latency, 3), "latency_max": round(max_latency, 3), "per_node_ok": dict(stats["per_node_ok"]), "per_node_fail": dict(stats["per_node_fail"]), "leaders_seen": dict(stats["leaders_seen"]), "results_csv": str(EVENTS_CSV)}}
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)


def print_stats():
    """Imprime stats finales del test."""
    with stats_lock:
        total = stats["events_total"]
        ok = stats["events_ok"]
        failed = stats["events_failed"]
        success_rate = ((ok / total) * 100) if total else 0
        avg_latency = (sum(stats["latency"]) / len(stats["latency"])) if stats["latency"] else 0
        max_latency = max(stats["latency"]) if stats["latency"] else 0
        min_latency = min(stats["latency"]) if stats["latency"] else 0
        p50_latency = percentile(stats["latency"], 50)
        p95_latency = percentile(stats["latency"], 95)
        p99_latency = percentile(stats["latency"], 99)
    print("\\n" + "=" * 56)
    print("FINAL CHAOS STATS v5")
    print("=" * 56)
    print(f"events_total........: {total}")
    print(f"events_ok...........: {ok}")
    print(f"events_failed.......: {failed}")
    print(f"success_rate........: {success_rate:.2f}%")
    print(f"latency_avg.........: {avg_latency:.1f} ms")
    print(f"latency_min.........: {min_latency:.1f} ms")
    print(f"latency_p50.........: {p50_latency:.1f} ms")
    print(f"latency_p95.........: {p95_latency:.1f} ms")
    print(f"latency_p99.........: {p99_latency:.1f} ms")
    print(f"latency_max.........: {max_latency:.1f} ms")
    print(f"stats_file..........: {STATS_FILE}")
    print(f"events_csv..........: {EVENTS_CSV}")
    print("=" * 56)


def main():
    """
    Entry point del chaos test.

    Secuencia:
        1. Arranca SEND_WORKERS workers
        2. Ejecuta chaos_loop() (genera eventos + mata nodos)
        3. Espera queue drain
        4. Espera kill threads
        5. Revive todos los nodos
        6. Escribe stats y imprime resumen
    """
    print(f"[MAIN] starting UNIVERSAL chaos torture final v5 ({ARGS.mode})")
    print_test_config()
    workers = []
    for idx in range(SEND_WORKERS):
        t = threading.Thread(target=sender_worker, args=(idx,), daemon=True)
        t.start()
        workers.append(t)
    drained = False
    try:
        chaos_loop()
        drained = wait_queue_drain()
        pending_queue.join()
        for t in workers:
            t.join(timeout=5)
    finally:
        wait_kills()
        revive_everything()
        if not drained:
            print(f"\\n[MAIN WARN] queue drain timeout reached after {DRAIN_TIMEOUT:.1f}s\\n")
        write_csv_and_json()
        print_stats()
        print("\\n[MAIN] cluster restored\\n")


if __name__ == "__main__":
    main()
