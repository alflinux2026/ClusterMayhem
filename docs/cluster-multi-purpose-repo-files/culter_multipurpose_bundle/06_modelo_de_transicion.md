# Culter Multi Purpose — Modelo de transición

## Estados de nodo
- `BOOT`
- `DISCOVERING`
- `STANDBY`
- `ACTIVE`
- `DEGRADED`
- `ISOLATED`
- `OFFLINE`

## Estados de evento
- `CREATED`
- `EXECUTING`
- `COMPLETED`
- `FAILED`

## Reglas
- `CREATED -> EXECUTING`.
- `EXECUTING -> COMPLETED`.
- `EXECUTING -> FAILED`.
- `EXECUTING -> CREATED` para retry o recovery.
- No se debe romper idempotencia al reinyectar eventos.

## Idea práctica
El core del cluster decide el ruteo y el worker ejecuta, pero la verdad persistente debe seguir siendo por stream y por evento individual.
