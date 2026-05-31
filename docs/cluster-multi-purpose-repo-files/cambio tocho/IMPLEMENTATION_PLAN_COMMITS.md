# IMPLEMENTATION_PLAN_COMMITS

> Plan de ejecución por commits para migrar el runtime a `StreamKey` + `EventEnvelope` + `NodeRuntimeState`.

## Commit 1 — `feat(runtime): introduce typed event and node runtime models`

### Objetivo
Introducir los modelos base que sustituyen las estructuras ambiguas por tipos explícitos.

### Archivos
- `cluster/runtime/events/cluster_event.py`
- `cluster/runtime/node_runtime.py`
- `cluster/runtime/state.py` si hace falta ajuste mínimo de enums.
- Imports afectados en `api_app.py`, `event_log.py`, `worker/event_worker.py`.

### Cambios
- `ClusterEvent` con `Field(default_factory=...)` para mutables.
- `NodeRuntimeState` como contenedor real del runtime.
- `NodeRuntime` usa `runtime_state` como fuente de verdad.

### Riesgo
Bajo-medio. Puede romper imports o accesos directos a atributos viejos.

### Validación
- El proyecto importa sin errores.
- `ClusterEvent` se serializa y deserializa correctamente.
- `NodeRuntime` arranca y transiciona de estado.

## Commit 2 — `feat(storage): add stream-keyed event log persistence`

### Objetivo
Reescribir la persistencia para que el almacenamiento deje de ser un log global y pase a ser por stream.

### Archivos
- `cluster/runtime/event_log.py`
- `cluster/runtime/models.py` o equivalentes si aún no existen.
- `cluster/runtime/serialization.py`
- `cluster/runtime/paths.py`
- `cluster/runtime/heartbeat_builder.py` si depende del storage.

### Cambios
- Introducir `StreamKey`.
- Introducir `EventEnvelope`.
- Introducir `SegmentMeta`.
- Persistencia por `current.jsonl`, `current.state.json` y `segments/`.
- `append_event()` y `replay_events()` adaptados a stream.

### Riesgo
Alto. Es el cambio estructural más grande del plan.

### Validación
- Se puede guardar un evento para un stream concreto.
- Se puede rehidratar el stream.
- Se puede leer metadata de append y de segmento.

## Commit 3 — `feat(api): propagate heartbeat streams through runtime`

### Objetivo
Hacer que el arranque y el heartbeat propaguen la identidad de stream desde el inicio.

### Archivos
- `cluster/runtime/node_boot.py`
- `cluster/runtime/context.py`
- `cluster/runtime/cluster_store.py`
- `cluster/runtime/api_app.py`

### Cambios
- Crear `StreamKey` desde config.
- Guardar el stream en `context`.
- Incluir `streams` en `Heartbeat`.
- Persistir `streams` en `cluster_state`.

### Riesgo
Medio. Normalmente rompe poco, pero afecta a todo el pipeline.

### Validación
- El nodo arranca con `StreamKey` definido.
- `/heartbeat` acepta y conserva `streams`.
- `ctx.stream` está disponible en el runtime.

## Commit 4 — `feat(pipeline): make dispatcher worker router reconciler stream-aware`

### Objetivo
Pasar el `StreamKey` por el pipeline de ejecución para que no dependa de un log global.

### Archivos
- `cluster/runtime/dispatcher.py`
- `cluster/runtime/worker/event_worker.py`
- `cluster/runtime/event_router.py`
- `cluster/runtime/reconciler/reconciler_loop.py`

### Cambios
- `dispatch_tick(stream=None)`.
- `dispatch_created_event(event, stream=None)`.
- `execute_event(event, stream=None)`.
- `forward_event(node_id, event, stream=None)`.
- `reconcile_tick(node_runtime, stream=None)`.

### Riesgo
Alto. Toca la ruta crítica de ejecución de eventos.

### Validación
- Un evento se despacha, ejecuta y completa usando el mismo stream.
- El reconciler recupera colgados en el stream correcto.
- No hay dependencia implícita de log global en el flujo principal.

## Commit 5 — `feat(core): align bootstrap leader integrity ingest with stream runtime`

### Objetivo
Ajustar el núcleo de soporte para que trabaje con el nuevo runtime sin acoplamientos viejos.

### Archivos
- `cluster/runtime/bootstrap.py`
- `cluster/runtime/leader.py`
- `cluster/runtime/integrity.py`
- `cluster/runtime/registry.py`
- `cluster/runtime/ingest.py`

### Cambios
- `bootstrap.py` genera config con `tenant_id`, `app_id`, `data_type`, `schema_version`.
- `leader.py` calcula vivos y líder sobre `cluster_state` coherente.
- `integrity.py` usa vistas y metadatos alineados con el runtime.
- `registry.py` queda como registro limpio.
- `ingest.py` marca origen/recepción y persiste correctamente.

### Riesgo
Medio. Suele haber imports y supuestos viejos escondidos.

### Validación
- `compute_leader()` sigue funcionando.
- `local_integrity_api()` devuelve datos coherentes.
- `ingest_event()` persiste y marca origen correctamente.

## Commit 6 — `feat(repl-state): align replication and state machine`

### Objetivo
Cerrar la compatibilidad de réplica y transición de estado con el nuevo modelo.

### Archivos
- `cluster/runtime/log_replication.py`
- `cluster/runtime/state_machine.py`

### Cambios
- Réplica alineada al almacenamiento por stream.
- Transición de eventos validada y persistida correctamente.

### Riesgo
Medio. Puede destapar estados intermedios que antes se toleraban.

### Validación
- La réplica no rompe el formato nuevo.
- Las transiciones inválidas se rechazan.
- Las transiciones válidas re-persisten el evento.

## Commit 7 — `refactor(core): clean imports and retire legacy log assumptions`

### Objetivo
Hacer limpieza final, quitar supuestos antiguos y dejar la migración cerrada.

### Archivos
- Todos los importes afectados.
- `cluster/runtime/event_log_00.py` si se quiere congelar o retirar.
- Legacy paralelo que ya no sea canónico.

### Cambios
- Limpiar imports rotos.
- Eliminar referencias a log global donde ya exista `StreamKey`.
- Marcar módulos viejos como legacy o retirar los que ya no se usan.

### Riesgo
Bajo-medio. Es limpieza, pero puede romper enlaces residuales.

### Validación
- El árbol importa sin advertencias graves.
- No quedan referencias críticas al modelo anterior.
- El runtime funciona con el nuevo contrato de evento y stream.

## Orden de ejecución recomendado

1. Commit 1.
2. Commit 2.
3. Commit 3.
4. Commit 4.
5. Commit 5.
6. Commit 6.
7. Commit 7.

## Regla de aceptación

No pasar al siguiente commit hasta que el anterior cumpla su validación mínima.

## Regla de oro

Si un archivo no sabe qué `StreamKey` maneja, todavía no está migrado.
Si un evento no puede persistirse y rehidratarse, todavía no está cerrado.
Si el runtime sigue leyendo un único JSONL global, todavía no has terminado.
