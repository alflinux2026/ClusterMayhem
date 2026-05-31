# Mayhem refactor map

## Objetivo

Reestructurar el runtime sin cambiar comportamiento observable:
- mismos endpoints,
- mismo flujo de eventos,
- mismo modelo líder/stand-by,
- misma convivencia entre nodos.

Regla:
- un cambio estructural por commit,
- smoke test tras cada commit,
- chaos corto si se toca dispatcher/router/worker/reconciler.

---

## Prioridad máxima

### `runtime/node_boot.py`
**Problema**
- Sigue concentrando demasiado: arranque, API, bootstrap, workers, runtime y contexto.

**Objetivo**
- Dejarlo como entrypoint fino.

**Debe quedar en**
1. cargar config,
2. construir runtime,
3. crear app,
4. lanzar workers,
5. arrancar servidor.

**Acción**
- Seguir sacando todo lo que no sea ensamblaje.

**Riesgo**
- Muy alto.

---

## Orden real de refactor

## Fase 1 — Bajo riesgo

### `utils/log_print.py`
**Dejar**
- solo helpers de log.

**Quitar**
- cualquier dependencia de runtime.

**Riesgo**
- bajo.

---

### `runtime/events/event_state.py`
**Dejar**
- enum y validaciones simples de estado.

**Quitar**
- lógica operativa.

**Riesgo**
- bajo.

---

### `runtime/events/cluster_event.py`
**Dejar**
- modelo `ClusterEvent` y defaults.

**Quitar**
- lógica de negocio o helpers metidos donde no toca.

**Riesgo**
- bajo.

---

### `runtime/state.py`
**Dejar**
- enum de estado de nodo.

**Quitar**
- cualquier lógica de transición.

**Riesgo**
- bajo.

---

### `runtime/registry.py`
**Dejar**
- registro estático/base del cluster.

**Quitar**
- nada importante por ahora.

**Riesgo**
- bajo.

---

## Fase 2 — Núcleo estable

### `runtime/bootstrap.py`
**Dejar**
- carga, descubrimiento y normalización de config.

**Quitar**
- lógica metida en `node_boot.py`.

**Riesgo**
- medio-bajo.

---

### `runtime/cluster_store.py`
**Dejar**
- estructura y acceso al estado compartido del cluster.

**Quitar**
- mutaciones dispersas hechas desde otros módulos.

**Riesgo**
- medio-bajo.

---

### `runtime/leader.py`
**Dejar**
- `compute_leader()` y helpers puros.

**Quitar**
- cualquier efecto lateral innecesario.

**Riesgo**
- medio-bajo.

---

### `runtime/event_log.py`
**Dejar**
- `append`, `load`, `replay` y persistencia de eventos.

**Quitar**
- helpers duplicados repartidos por otros módulos.

**Riesgo**
- medio-bajo.

---

### `runtime/state_machine.py`
**Dejar**
- validación y transición de estados.

**Quitar**
- lógica desperdigada en dispatcher/router/worker.

**Riesgo**
- medio-bajo.

---

## Fase 3 — Borde de entrada

### Extraer API fuera de `runtime/node_boot.py`
**Crear**
- `api/app.py`
- `api/routes_health.py`
- `api/routes_cluster.py`
- `api/routes_leader.py`
- `api/routes_control.py`
- `api/routes_event.py`

**Objetivo**
- sacar FastAPI, modelos HTTP y rutas fuera de `node_boot.py`.

**Riesgo**
- medio.

---

### `runtime/node_boot.py`
**Dejar**
- solo wiring de arranque.

**Quitar**
- rutas,
- modelos request/response,
- lógica HTTP,
- helpers de ejecución que no sean de bootstrap.

**Riesgo**
- muy alto.

---

## Fase 4 — Ejecución distribuida

### `runtime/ingest.py`
**Dejar**
- validación e inserción del evento en el flujo.

**Quitar**
- decisiones de transporte mezcladas si ensucian el módulo.

**Riesgo**
- medio.

---

### `runtime/worker/event_worker.py`
**Dejar**
- ejecución del trabajo y actualización de estado.

**Quitar**
- lógica de scheduler o coordinación.

**Riesgo**
- medio.

---

### `runtime/reconciler/reconciler_loop.py`
**Dejar**
- solo reconciliación.

**Quitar**
- control de threads o scheduling.

**Riesgo**
- medio.

---

### `runtime/node_worker.py`
**Dejar**
- loops, ticks, ciclo de vida del worker.

**Quitar**
- lógica de negocio de dispatch o reconciler.

**Riesgo**
- medio.

---

### `runtime/dispatcher.py`
**Dejar**
- decisión de qué evento procesar y cuándo.

**Quitar**
- transporte puro,
- persistencia metida directamente,
- helpers mezclados con forwarding.

**Riesgo**
- alto.

---

### `runtime/event_router.py`
**Dejar**
- routing y forwarding.

**Quitar**
- duplicidades,
- mezcla excesiva de red + persistencia + topología.

**Riesgo**
- alto.

---

## Fase 5 — Final delicado

### `node/node_runtime.py`
**Dejar**
- estado vivo y operaciones nucleares del nodo.

**Quitar**
- llamadas HTTP directas si no son parte de su responsabilidad real.

**Riesgo**
- medio-alto.

---

### `runtime/context.py`
**Dejar**
- estado global mínimo imprescindible.

**Quitar**
- acceso directo disperso, pero al final del proceso.

**Riesgo**
- muy alto.

**Nota**
- tocarlo solo cuando el resto ya esté más limpio.

---

## Orden exacto de commits

1. `utils/log_print.py`
2. `runtime/events/event_state.py`
3. `runtime/events/cluster_event.py`
4. `runtime/state.py`
5. `runtime/registry.py`
6. `runtime/bootstrap.py`
7. `runtime/cluster_store.py`
8. `runtime/leader.py`
9. `runtime/event_log.py`
10. `runtime/state_machine.py`
11. extraer API fuera de `runtime/node_boot.py`
12. adelgazar `runtime/node_boot.py`
13. `runtime/ingest.py`
14. `runtime/worker/event_worker.py`
15. `runtime/reconciler/reconciler_loop.py`
16. `runtime/node_worker.py`
17. `runtime/dispatcher.py`
18. `runtime/event_router.py`
19. `node/node_runtime.py`
20. `runtime/context.py`

---

## Estructura destino recomendada

```text
cluster/
  api/
    app.py
    routes_health.py
    routes_cluster.py
    routes_leader.py
    routes_control.py
    routes_event.py

  node/
    node_runtime.py

  runtime/
    bootstrap.py
    factory.py
    cluster_store.py
    context.py
    dispatcher.py
    event_log.py
    event_router.py
    ingest.py
    leader.py
    node_boot.py
    node_worker.py
    registry.py
    state.py
    state_machine.py

    events/
      cluster_event.py
      event_state.py

    reconciler/
      reconciler_loop.py

    worker/
      event_worker.py

  utils/
    log_print.py
```

---

## Qué hacer con `no_core`

### Usarlo para
- referencia de organización,
- ideas de modularización,
- posibles destinos futuros.

### No usarlo para
- reinyectarlo a medias dentro del runtime actual.

---

## Checklist por commit

- un solo objetivo estructural,
- sin cambiar contrato externo,
- imports corregidos,
- sin duplicidades obvias,
- `/health` OK,
- `/leader` OK,
- `/cluster` OK,
- chaos corto si se tocó dispatcher/router/worker/reconciler.

---

## Siguiente paso recomendado

Siguiente movimiento:
1. terminar de sacar la API de `runtime/node_boot.py`,
2. dejar `node_boot.py` como ensamblador puro,
3. luego limpiar `event_log`, `leader` y `cluster_store`.
