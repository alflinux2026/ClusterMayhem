# Culter Multi Purpose — Flujo operativo

## Ingesta
1. Llega un evento.
2. Se resuelve `StreamKey`.
3. Se envuelve en `EventEnvelope`.
4. Se escribe en el segmento activo del stream.

## Rotación
1. El segmento supera umbral de tamaño o edad.
2. Se sella.
3. Se calcula `sha256`.
4. Se crea el siguiente segmento.
5. Se actualiza el heartbeat.

## Réplica
1. El nodo solo replica segmentos sellados.
2. Los peers reciben ficheros cerrados e inmutables.
3. Si el peer replica correctamente, se limpia el estado `dirty`.

## Reconciliación
- Si un evento no acaba en estado terminal, el reconciler lo reevalúa.
- La decisión se toma por `event_id` y no por posición física en el log.

## Ventaja
Se reduce el coste de comparar ficheros grandes y se mejora la trazabilidad por tipo de dato.
