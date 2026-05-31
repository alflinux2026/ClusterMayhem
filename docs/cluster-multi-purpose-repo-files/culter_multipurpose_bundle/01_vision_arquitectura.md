# Culter Multi Purpose — Visión de arquitectura

## Objetivo
El sistema debe soportar múltiples aplicaciones y múltiples tipos de datos sobre un core común, sin mezclar semánticas incompatibles.

## Principios
- Un core común para ingestión, réplica, reconciliación y heartbeat.
- Separación lógica por `tenant_id`, `app_id`, `data_type` y `schema_version`.
- Segmentos físicos inmutables una vez sellados.
- Integridad verificable por hash.
- Replay determinista por stream.

## Unidades principales
- `StreamKey`: identidad lógica del flujo.
- `EventEnvelope`: envoltorio de evento de negocio.
- `SegmentMeta`: metadata del segmento físico.
- `HeartbeatState`: resumen del nodo para el cluster.
- `NodeState`: estado operativo del nodo y su visión del cluster.

## Decisión clave
No se debe usar un log genérico único para todo. El core puede ser único, pero el almacenamiento y el heartbeat deben hablar en términos de streams tipados.
