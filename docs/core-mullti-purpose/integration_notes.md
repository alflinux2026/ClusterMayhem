# Integración NodeRuntimeState

## Objetivo
Sustituir el uso ambiguo de estructuras genéricas por `NodeRuntimeState` en el runtime real y en el builder del heartbeat.

## Cambios recomendados
- `NodeRuntime` debe exponer una instancia `runtime_state: NodeRuntimeState`.
- `emit_heartbeat()` debe construir el heartbeat desde `runtime_state`.
- `clusterstate` debe almacenar la vista del nodo usando `NodeRuntimeState` serializable.
- Los endpoints HTTP deben leer el estado desde esa única estructura.

## Mapeo sugerido
- `ctx.node.state` -> `runtime_state.state`
- `ctx.node.priority` -> `runtime_state.priority`
- `ctx.node.last_seen` -> `runtime_state.last_seen`
- `ctx.node.log_meta` -> `runtime_state.log_meta`
- `ctx.node.cluster_integrity` -> `runtime_state.cluster_integrity`
- `ctx.node.active_streams` -> `runtime_state.active_streams`

## Resultado esperado
Un solo objeto fuente de verdad para el estado del nodo, con serialización directa al heartbeat.
