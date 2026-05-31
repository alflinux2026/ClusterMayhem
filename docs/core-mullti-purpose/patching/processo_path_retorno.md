# Culter Multi Purpose — Proceso de path para retomarlo después

## Objetivo
Dejar documentado el camino exacto de integración para que el sistema pase de un log genérico a un modelo por `stream_id`, con nodos, heartbeat, segmentación e integridad.

## Fase 1 — Base conceptual
- Definir `tenant_id`, `app_id`, `data_type` y `schema_version`.
- Construir `StreamKey` como identidad lógica del flujo.
- Separar el dato de negocio en `EventEnvelope`.
- Separar metadata física en `SegmentMeta`.
- Separar estado del nodo en `NodeRuntimeState`.

## Fase 2 — Modelo Python
- Crear `models.py` con los tipos base.
- Crear `serialization.py` para convertir modelos a diccionario y обратно.
- Crear `paths.py` para rutas por stream.
- Crear `heartbeat_builder.py` para generar el heartbeat desde el runtime.

## Fase 3 — Estructura de ficheros
- `cluster/data/<tenant>/<app>/<type>/<version>/current.jsonl`.
- `cluster/data/<tenant>/<app>/<type>/<version>/current.state.json`.
- `cluster/data/<tenant>/<app>/<type>/<version>/segments/<segment_id>.jsonl`.
- `cluster/data/<tenant>/<app>/<type>/<version>/segments/<segment_id>.meta.json`.

## Fase 4 — Integración runtime
- Cambiar `NodeRuntime` para usar `NodeRuntimeState`.
- Hacer que `emit_heartbeat()` use el estado runtime como fuente única de verdad.
- Ajustar `apiapp.py` para leer y escribir heartbeat con ese modelo.
- Mantener compatibilidad temporal con lo que ya hay.

## Fase 5 — Almacenamiento
- Parchear `eventlog.py` para escribir por `stream_id`.
- Guardar estado de append por stream.
- Añadir `append_event()`.
- Añadir `seal_segment()` para persistir `SegmentMeta`.

## Fase 6 — Ejecución por stream
- Ajustar `dispatcher.py` para leer eventos creados por stream.
- Ajustar `reconciler_loop.py` para recuperar colgados por stream.
- Ajustar `eventworker.py` para completar `EventEnvelope`.
- Ajustar `eventrouter.py` para reenviar eventos serializados por stream.
- Ajustar `NodeWorker` para ejecutar las mismas fases sin depender de una cola global.

## Fase 7 — Docs
- Copiar toda la documentación técnica a `docs/`.
- Añadir `docs/CHANGELOG.md` con decisiones cerradas.
- Mantener un índice en `docs/README.md`.

## Orden recomendado si se retoma más tarde
1. Revisar `models.py`.
2. Revisar `serialization.py`.
3. Revisar `paths.py`.
4. Integrar `NodeRuntimeState` en `NodeRuntime`.
5. Parchear `eventlog.py`.
6. Parchear `dispatcher`, `reconciler`, `worker`.
7. Parchear `eventrouter` y `NodeWorker`.
8. Ejecutar tests de coherencia de path, replay e integridad.

## Riesgos
- Mezclar nombres de estado entre enum y dataclass.
- Olvidar el `stream_id` en un endpoint y volver a caer en el log global.
- Actualizar el heartbeat sin actualizar el estado persistente.
- Dejar un módulo viejo apuntando a estructuras antiguas.

## Regla de oro
Si una pieza no sabe a qué `stream_id` pertenece, todavía no está bien integrada.
