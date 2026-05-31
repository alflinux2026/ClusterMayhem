# CHANGELOG de decisiones técnicas

## 2026-05-22

### Añadido
- Separación del diseño en `StreamKey`, `EventEnvelope`, `SegmentMeta`, `HeartbeatState` y `NodeState`.
- Convención de ficheros por `tenant_id`, `app_id`, `data_type` y `schema_version`.
- Segmentación de logs por tamaño y por tipo de dato.
- Heartbeat con `log_meta`, `cluster_integrity` y resumen por stream.
- Estrategia de migración sin romper compatibilidad inmediata con `ClusterEvent`.

### Decisiones cerradas
- El core será común, pero los streams serán tipados y separados.
- Los segmentos sellados serán inmutables.
- Solo se replicarán segmentos sellados.
- El heartbeat representará el estado por stream, no solo por nodo.
- No se mezclará más de un tipo semántico de dato en un mismo stream físico.

### Pendiente
- Implementar el adaptador `ClusterEvent <-> EventEnvelope`.
- Reescribir `eventlog.py` para rutas por stream.
- Extender la lógica de réplica para segmentos con metadata y hash.
- Añadir validación de schemas y compatibilidad entre versiones.
