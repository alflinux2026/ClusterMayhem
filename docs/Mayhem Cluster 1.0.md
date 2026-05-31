***

# Mayhem Cluster 1.0

Última actualización: 2026-05-28  
Autor: alftorres

## Tabla de contenidos

- Visión general
- Arquitectura
- Estados y maquina de nodos
- Modelo de eventos
- Gestión de logs y replicación
- Segmentación y rotación
- Leader election y heartbeats
- API HTTP (endpoints principales)
- Workers y loop runtime
- Testing de caos (chaos torture)
- Monitorización y utilidades
- Scripts de análisis y packaging
- Cómo desplegar y ejecutar
- Referencia rápida de módulos

***

## Visión general

Mayhem Cluster es un runtime distribuido ligero para ingestión y procesamiento de eventos con replicación y tolerancia a fallos. Está diseñado para:

- Mantener un log de eventos local por nodo y réplicas remotas.
- Elegir un líder entre nodos por prioridad.
- Replicar logs y eventos para durabilidad y recuperación.
- Rotar (segmentar) logs cuando alcanzan un umbral para evitar archivos enormes.
- Detectar nodos “ocupados” o “stale” mediante watchdog y heartbeats.
- Proveer una API HTTP para control, debugging y extracción de datos.

Principios de diseño:
- Simplicidad: archivos JSONL para eventos y logs.
- Observabilidad: endpoints /dashboard y utilidades TUI / snapshots.
- Resiliencia: retries, reintentos y restauración automática.

***

## Arquitectura

Estructura principal del proyecto (resumen):

- runtime/: runtime del nodo (entrypoint, state machine, API, log handling)
  - node_boot.py — entrypoint que inicia el nodo y el servidor HTTP
  - node_runtime.py — definición de Node, estados (NodeState) y transiciones
  - node_worker.py — worker en background que ejecuta ticks periódicos
  - api_app.py — FastAPI con endpoints para eventos, heartbeats, watchdogs, debug, integridad
  - event_log.py — lectura/escritura de logs locales, repuestos y completed
  - log_replication.py — lógica de replicación (replicar eventlog y events)
  - leader.py — compute_leader() y reglas de elección
  - cluster_store.py — cluster_state: store en memoria compartida
  - events/: modelo y estado de eventos
    - cluster_event.py — Pydantic ClusterEvent
    - event_state.py — EventStatus enum y validate_transition()
- utils/: utilidades para devops y testing
  - chaos/: torture runner para tests de caos (chaos_torture.py)
  - cluster_live.py — monitor TUI + snapshot remoto
- scripts/: análisis estático, bundling y snapshot de “core” del repo

Comunicación:
- Nodos se comunican por HTTP (puerto 7000 por defecto).
- Endpoint /event recibe eventos; si el nodo es STANDBY se reenvía al líder.

***

## Estados y máquina de nodos

Estados definidos (NodeState):
- BOOT — arranque, bootstrap de caché de eventos y transición a STANDBY.
- DISCOVERING — descubrimiento de peers (placeholder).
- STANDBY — estado normal, replica logs y responde a heartbeats.
- ACTIVE — líder; hace trabajo de coordinación (similar a STANDBY en tick).
- SEGMENTATION — en proceso de rotar (archivar) segment local.
- DRAINING — preparar para segmentación (cuando número de events > MAX_SEGMENT_COUNT).
- ISOLATED — sleep / nodo aislado (no participa).
- OFFLINE — desconectado (placeholder).

Comportamiento:
- NodeWorker ejecuta un loop con tick() y despacha tick_* por estado. (node_worker.py)
- Heartbeats actualizan cluster_state con last_seen, state, priority, streams y cluster_integrity.
- Watchdog se emite periódicamente para indicar busy=True cuando el nodo procesa.

Parámetros importantes por entorno:
- EVENTSTATECHECKPERIODSEC (default 10s)
- STATEDEBUGPERIODSEC (default 30s)
- MAX_SEGMENT_COUNT (default 2500)

***

## Modelo de eventos

ClusterEvent (cluster/runtime/events/cluster_event.py)
- Pydantic BaseModel con campos:
  - event_id, trace_id (UUID)
  - schema_version, event_type
  - payload (dict)
  - status: EventStatus (CREATED, EXECUTING, COMPLETED, FAILED)
  - route_hops: lista de nodos por donde pasó
  - source_node, target_node
  - created_at, updated_at, received_at
  - attempt, execution_key
- Métodos:
  - add_hop(hop)
  - mark_status(status)
  - mark_received()

EventStatus y validación (cluster/runtime/events/event_state.py)
- Enum: CREATED, EXECUTING, COMPLETED, FAILED
- VALID_TRANSITIONS define transiciones permitidas:
  - CREATED -> EXECUTING
  - EXECUTING -> COMPLETED | FAILED | CREATED (retry)
  - COMPLETED -> (nada)
  - FAILED -> (nada)
- validate_transition(old, new) lanza ValueError si no es permitida, permita idempotencia (old==new no-op).

***

## Gestión de logs y replicación

Ficheros y rutas:
- events.local.000.jsonl — eventos locales activos
- event_log.local.000.jsonl — log local de eventos (replicable)
- events.{node}.{idx}.jsonl — archivos rotados/replicados
- event_log.{node}.{idx}.jsonl — archivos de log rotados/replicados
- completed.jsonl — eventos completados

Funciones clave:
- load_events(), load_completed_events(), rebuild_event_state_index() (event_log.py)
- get_local_log_path(), get_replica_log_path(), get_replica_events_path(), get_completed_log_path()

Replicación:
- replicate_eventlog() y replicate_events() son llamadas periódicamente desde ticks (node_worker.tick_standby/active).
- Cuando se detecta dirty en cluster_integrity, la replicación intentará sanar diferencias.

Integridad:
- cluster/runtime/integrity.py (local_integrity_api(), cluster_integrity_report()) calcula checks y meta del log.
- cluster_state guarda cluster_integrity por nodo.

***

## Segmentación y rotación

Objetivo: evitar archivos JSONL gigantes moviendo .local.000 a .{node}.{idx}.jsonl

Control:
- _node_event_counters() obtiene counts desde cluster_state streams (events_summary_local).
- _can_segment(node): solo segmentar si created > 0, executing == 0 y cache.dirty == False.
- _should_enter_DRAINING(node): enters DRAINING si total_events > MAX_SEGMENT_COUNT.
- _should_enter_segmentation(node): consulta _can_segment (política simple).

Acciones:
- rotate_segment_files(target_group, segment="000", files=["events","event_log"], force=False)
  - Renombra .local.000 -> .{node}.{idx}.jsonl, calcula idx con _next_rotation_index().
- cleanup_local_segment_files(node_id, segment="000", files=...) borra archivos locales tras rotación.

Transiciones:
- STANDBY/ACTIVE detectan exceso y pasan a DRAINING.
- DRAINING cuando _should_enter_segmentation() pasa a SEGMENTATION.
- SEGMENTATION ejecuta rotate_segment_files, cleanup y vuelve a STANDBY.

***

## Leader election y heartbeats

Leader election:
- compute_leader() (cluster/runtime/leader.py) determina líder usando prioridad y salud (heartbeat/watchdog).
- Heartbeat model (api_app.Heartbeat) incluye node_id, state, priority, state_since, prev_state, state_reason, log_meta, cluster_integrity, streams.

Heartbeats y watchdogs:
- /heartbeat endpoint actualiza cluster_state[node_id] con last_seen, state, priority, streams, cluster_integrity.
- /watchdog endpoint actualiza last_watchdog y watchdog_busy.
- emit_watchdog_if_due(peers, busy=True) enviado periódicamente por NodeWorker.

Health / presence:
- _presence_age_s() y _presence_health() en api_app calculan si un nodo es "ok" o "stale" (por defecto stale_after_s=3s).

***

## API HTTP (endpoints principales)

Servidor: FastAPI (cluster/runtime/api_app.py)

Debug / logs:
- GET /debug/log — devuelve log local
- GET /debug/log/local — alias
- GET /debug/log/completed — log de completados
- GET /debug/log/replica/{node_id} — log replica de peer
- POST /debug/log/replica/{node_id} — escribir replica (replication push)
- POST /debug/events/replica/{node_id} — escribir events replica

Events:
- POST /event — recibe evento ClusterEvent
  - Si nodo en SEGMENTATION/DRAINING/ISOLATED retorna error
  - Si no hay líder retorna error
  - Si estado STANDBY: reenvía el evento al líder por HTTP (CLUSTER_REGISTRY)
  - Si líder: llama ingest_event(event, ctx.node_id)
- POST /ack — ACK simple (logging)
- POST /replay — replay_events(handler, ctx.stream) (handler vacío en endpoint)

Control:
- POST /sleep — transiciona a ISOLATED (sleep command)
- POST /revive — transiciona a BOOT (wake up)

Health / cluster info:
- GET /health — health local (presence, watchdog, state_age, sleeping)
- GET /cluster — devuelve cluster_state compactado por nodo
- GET /leader — devuelve current leader
- GET /dashboard/compact — dashboard completo con nodes[], local events summary, integrity, progress
- GET /integrity — integridad local
- GET /integrity/cluster — integridad de cluster

Segmentación remota:
- POST /segment/rotate — rota archivos .local.000 -> .{target_group}.{idx}.jsonl (usa rotate_segment_files)

Modelo de datos:
- Heartbeat (Pydantic), Watchdog, SegmentRotateRequest

***

## Workers y loop runtime

NodeWorker (cluster/runtime/node_worker.py)
- Instancia por nodo que corre en un hilo daemon:
  - start(): lanza thread con target loop()
  - loop(): mientras running:
    - node.tick()
    - log_state_runtime_debug(node) (cada STATEDEBUGPERIODSEC)
    - si node.state == ISOLATED -> continue
    - _tick_by_state() -> dispatch a tick_boot / tick_standby / tick_active / tick_segmentation / tick_DRAINING / ...
    - sleep(interval) (interval por defecto 1s)

tick_* resumen:
- tick_boot():
  - emit_watchdog_if_due(peers, busy=True)
  - rebuild_node_event_cache(node.node_id)
  - node.event_cache_ready = True
  - node.transition(STANDBY, reason="boot_complete")
- tick_standby() y tick_active():
  - emit heartbeat
  - emit watchdog busy
  - replicate_eventlog(), replicate_events()
  - leader_event_state_check_tick()
  - si _should_enter_DRAINING -> node.transition(DRAINING)
- tick_segmentation():
  - if should_seg: rotate_segment_files(...), cleanup_local_segment_files, rebuild_node_event_cache, transition(STANDBY)
- tick_DRAINING():
  - replica logs, rebuild_node_event_cache, leader_event_state_check_tick(), si _should_enter_segmentation -> transition(SEGMENTATION)

Caches por nodo:
- rebuild_node_event_cache(node_id): lee local events y completed events, summariza por status y actualiza cluster_state[node_id]["streams"].

***

## Testing de caos (chaos torture)

Herramienta: utils/chaos/chaos_torture.py

Propósito:
- Generar carga de eventos (miles o cientos de miles).
- Matar/revivir nodos aleatoriamente (POST /sleep y /revive) para evaluar resiliencia.
- Reintentos con backoff exponencial.
- Mide latencias, success rate, percentiles, y genera output (stats.json, events.csv).

Modo:
- smoke, benchmark, torture (presets)
Parámetros destacados:
- send_workers (hilos concurrentes)
- kill_prob (probabilidad de matar nodo por evento)
- retry_backoff_base/max, max_retries
- slow-ms: umbral para marcar eventos lentos

Salida:
- OUT_DIR/ stats.json y events.csv
- Estadísticas detalladas: per_node_ok, per_node_fail, latency list, leaders_seen, slow_events, unexpected_failures

***

## Monitorización y utilidades

cluster_live.py (utils/cluster_live.py)
- TUI curses que:
  - Se conecta por SSH a cada nodo y ejecuta ls -lb --full-time en el directorio de datos para listar event_log* y events*.
  - Se conecta a la API de cada nodo (/dashboard/compact, /health, /integrity, /debug/events/summary).
  - Muestra resumen en consola con colores (health, state, watchdog_age, progress, counts).
  - Permite snapshot (guardar markdown y json) pulsando 's'.
  - Tecla 'q' para salir.
- Genera archivos:
  - cluster_data_remote_inventory.md
  - cluster_data_remote_inventory.csv
  - cluster_data_remote_api_snapshot.json
  - snapshots/cluster_live_snapshot_YYYYMMDD_HHMMSS.{md,json}

Funciones clave:
- ssh_ls(node): usa paramiko para listar directorio remoto
- parse_ls_output / parse_ev_output: parse output de ls y extrae archivos relevantes
- fetch_api_snapshot(node): llama API remota y agrega info
- _node_runtime_view(api_snapshots, node_name): consolida info remota y local para mostrar mejor vista del nodo

***

## Scripts de análisis y packaging

Scripts para construir un “bundle” del core y snapshots:
- scripts/analyze_core.sh: análisis estático de imports (AST) para inferir core a partir de un entrypoint (node_boot.py). Genera:
  - core_files.txt (archivos alcanzables por imports)
  - no_core_files.txt (resto)
  - last_code_core.code / last_code_no_core.code (bundles con nl)
  - header_last_code_core.code / header_last_code_no_core.code (imports/defs)
  - core_summary.md (resumen)
- scripts/build_core_lite.sh: versión “lite” que toma una whitelist manual core-files-lite.txt y construye bundles y headers.

Detalles:
- El análisis de core usa AST para extraer import/ImportFrom y resolver módulos internos; resuelve imports relativos; realiza BFS recursivo desde entrypoint.
- El header se construye extrayendo líneas con import / from / def / class desde el bundle numerado.

***

## Cómo desplegar y ejecutar

Requisitos:
- Python 3.10+ (se usan typing union | y Pydantic)
- FastAPI + uvicorn
- requests, paramiko para utilidades y testing
- Entorno con permisos en carpeta data y puerto 7000 disponible

Paso a paso (nodo por nodo):
1. Instalar dependencias:
   pip install -r requirements.txt
   (requests, fastapi, pydantic, uvicorn, paramiko)

2. Configurar contexto (si procede):
   - Asegurar que cluster/runtime/context.py contiene node_id, node host/port y peers/CLUSTER_REGISTRY
   - Configurar directorio data con permisos

3. Iniciar nodo (ejemplo):
   python -m uvicorn cluster.runtime.api_app:app --host 0.0.0.0 --port 7000 --reload
   o usar node_boot.py que arranca node_runtime y worker

4. Verificar:
   - GET /health
   - GET /dashboard/compact
   - GET /leader

5. Enviar eventos:
   - POST /event con el payload de ClusterEvent (ver ejemplo en chaos_torture.py)

Prácticas recomendadas:
- Montar directorio data en volumen persistente.
- Supervisar disco y rotación de logs (MAX_SEGMENT_COUNT configurable vía env).
- Usar el chaos_torture en entornos de staging para validar tolerancia a fallos.

***

## Referencia rápida de módulos (resumen)

- cluster/runtime/node_boot.py — entrypoint que crea ctx.node, registra CLUSTER_REGISTRY y arranca uvicorn o worker.
- cluster/runtime/node_runtime.py — Node runtime: atributos node_id, state, tick(), transition(), emit_heartbeat()
- cluster/runtime/node_worker.py — NodeWorker: implementa loop, tick handlers, segmentación, replicación periódica.
- cluster/runtime/api_app.py — FastAPI app con endpoints de logs, eventos, heartbeat, watchdog, segment/rotate, health, dashboard, integrity.
- cluster/runtime/events/cluster_event.py — Pydantic ClusterEvent model.
- cluster/runtime/events/event_state.py — EventStatus enum y validate_transition.
- cluster/runtime/event_log.py — utilidades para leer/escribir eventos JSONL, reconstruir índices y replay.
- cluster/runtime/log_replication.py — replicación de eventlog y events (invocado en ticks).
- cluster/runtime/leader.py — lógica para determinar compute_leader().
- cluster/runtime/integrity.py — funciones de integridad local/cluster (checksums, last_append_meta).
- cluster/runtime/cluster_store.py — cluster_state (dict compartido en memoria).
- utils/chaos/chaos_torture.py — stress tester para el cluster.
- utils/cluster_live.py — TUI + snapshots por SSH y API.
- scripts/analyze_core.sh — análisis de core por imports (AST).
- scripts/build_core_lite.sh — bundle desde whitelist manual.

***

