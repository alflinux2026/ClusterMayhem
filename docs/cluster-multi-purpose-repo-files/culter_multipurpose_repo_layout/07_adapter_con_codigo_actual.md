# Culter Multi Purpose — Adaptación al código actual

## Lo que ya existe
- `ClusterEvent` como evento de negocio.
- `NodeRuntime` con estado y heartbeat.
- `eventlog.py` con append y replay.
- `dispatcher.py`, `reconciler_loop.py`, `worker.py` y `logreplication.py`.

## Qué cambiar
- Introducir `StreamKey` en el evento.
- Separar paths por `tenant/app/type/version`.
- Extender heartbeat con `log_meta` y `streams`.
- Calcular hash por segmento sellado.

## Estrategia de migración
1. Mantener compatibilidad con `ClusterEvent`.
2. Añadir `EventEnvelope` como capa nueva.
3. Adaptar `eventlog.append_event()` para serializar por stream.
4. Actualizar réplica para operar sobre segmentos cerrados.
5. Extender integridad e inspección del cluster.

## Riesgo principal
Mezclar streaming lógico con almacenamiento físico genérico otra vez. Eso hay que evitarlo sin piedad.
