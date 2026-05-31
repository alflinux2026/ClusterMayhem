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
- chaos corto si se toca dispatcher/router/worker/reconciler,
- cada archivo refactorizado debe quedar documentado con comentarios exhaustivos.

---

## Norma de documentación por archivo

Cada archivo refactorizado debe incluir:

### 1. Cabecera de archivo
Debe explicar:
- propósito del archivo,
- responsabilidad dentro del sistema,
- relación con otros módulos,
- qué no debe hacer ese archivo.

### 2. Comentarios por bloque
Cada bloque relevante debe explicar:
- qué hace,
- por qué existe,
- qué entradas espera,
- qué efectos laterales tiene,
- qué riesgos tiene si se modifica.

### 3. Comentarios en funciones
Cada función importante debe indicar:
- objetivo,
- flujo general,
- precondiciones,
- postcondiciones,
- efectos sobre estado global, event log o cluster state.

### 4. Comentarios especiales obligatorios
Añadir comentarios explícitos cuando toque:
- acceso a `context`,
- decisiones de liderazgo,
- mutaciones de `cluster_store`,
- escritura o replay de `event_log`,
- forwarding entre nodos,
- reconciliación,
- zonas sensibles a concurrencia,
- zonas sensibles a imports circulares.

### 5. Regla de calidad
Los comentarios deben explicar intención y arquitectura.
No deben limitarse a describir literalmente la línea de código.

Ejemplo malo:
- `# increment counter`

Ejemplo bueno:
- `# Este contador limita el número de reintentos locales antes de delegar el evento`
- `# al líder, evitando bucles de forwarding en nodos standby.`

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
- Añadir comentarios exhaustivos de arranque y wiring.

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

**Documentar**
- formato de salida,
- uso previsto,
- por qué debe permanecer agnóstico del cluster.

**Riesgo**
- bajo.

---

### `runtime/events/event_state.py`
**Dejar**
- enum y validaciones simples de estado.

**Quitar**
- lógica operativa.

**Documentar**
- significado exacto de cada estado,
- transiciones válidas,
- impacto funcional de cada estado.

**Riesgo**
- bajo.

---

### `runtime/events/cluster_event.py`
**Dejar**
- modelo `ClusterEvent` y defaults.

**Quitar**
- lógica de negocio o helpers metidos donde no toca.

**Documentar**
- semántica de cada campo,
- origen del `event_id`,
- papel del timestamp,
- relación entre evento y estado.

**Riesgo**
- bajo.

---

### `runtime/state.py`
**Dejar**
- enum de estado de nodo.

**Quitar**
- cualquier lógica de transición.

**Documentar**
- significado operativo de cada estado del nodo,
- diferencias entre standby, active, sleeping, isolated o equivalentes.

**Riesgo**
- bajo.

---

### `runtime/registry.py`
**Dejar**
- registro estático/base del cluster.

**Quitar**
- nada importante por ahora.

**Documentar**
- estructura esperada,
- quién la consume,
- qué parte es configuración y qué parte es estado derivado.

**Riesgo**
- bajo.

---

## Fase 2 — Núcleo estable

### `runtime/bootstrap.py`
**Dejar**
- carga, descubrimiento y normalización de config.

**Quitar**
- lógica metida en `node_boot.py`.

**Documentar**
- orden de bootstrap,
- fuentes de configuración,
- valores esperados,
- fallback y comportamiento de inicialización.

**Riesgo**
- medio-bajo.

---

### `runtime/cluster_store.py`
**Dejar**
- estructura y acceso al estado compartido del cluster.

**Quitar**
- mutaciones dispersas hechas desde otros módulos.

**Documentar**
- estructura interna del store,
- significado de cada campo,
- reglas de actualización,
- riesgos de concurrencia.

**Riesgo**
- medio-bajo.

---

### `runtime/leader.py`
**Dejar**
- `compute_leader()` y helpers puros.

**Quitar**
- cualquier efecto lateral innecesario.

**Documentar**
- criterio exacto de elección,
- dependencias del cálculo,
- comportamiento ante empate o nodos no visibles.

**Riesgo**
- medio-bajo.

---

### `runtime/event_log.py`
**Dejar**
- `append`, `load`, `replay` y persistencia de eventos.

**Quitar**
- helpers duplicados repartidos por otros módulos.

**Documentar**
- formato persistido,
- orden esperado,
- semántica de replay,
- riesgos de corrupción o duplicado.

**Riesgo**
- medio-bajo.

---

### `runtime/state_machine.py`
**Dejar**
- validación y transición de estados.

**Quitar**
- lógica desperdigada en dispatcher/router/worker.

**Documentar**
- tabla mental de transiciones,
- reglas inválidas,
- por qué algunas transiciones se rechazan.

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

**Documentar**
- contrato de cada endpoint,
- payload esperado,
- respuesta esperada,
- efecto sobre runtime o cluster.

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

**Documentar**
- secuencia completa de arranque,
- dependencias entre componentes,
- orden obligatorio de inicialización,
- por qué ese orden no debe alterarse sin test.

**Riesgo**
- muy alto.

---

## Fase 4 — Ejecución distribuida

### `runtime/ingest.py`
**Dejar**
- validación e inserción del evento en el flujo.

**Quitar**
- decisiones de transporte mezcladas si ensucian el módulo.

**Documentar**
- punto de entrada del evento,
- qué hace el líder,
- qué hace un standby,
- cuándo se persiste,
- cuándo se reenvía.

**Riesgo**
- medio.

---

### `runtime/worker/event_worker.py`
**Dejar**
- ejecución del trabajo y actualización de estado.

**Quitar**
- lógica de scheduler o coordinación.

**Documentar**
- ciclo de ejecución del evento,
- estados intermedios,
- manejo de errores,
- criterio de marcado como completado o fallido.

**Riesgo**
- medio.

---

### `runtime/reconciler/reconciler_loop.py`
**Dejar**
- solo reconciliación.

**Quitar**
- control de threads o scheduling.

**Documentar**
- por qué existe el reconciler,
- qué inconsistencias corrige,
- qué señales busca,
- qué riesgos tiene reconciliar de más.

**Riesgo**
- medio.

---

### `runtime/node_worker.py`
**Dejar**
- loops, ticks, ciclo de vida del worker.

**Quitar**
- lógica de negocio de dispatch o reconciler.

**Documentar**
- frecuencia del loop,
- orden de ejecución de ticks,
- condición de parada,
- dependencias con el estado del nodo.

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

**Documentar**
- criterio de selección de eventos,
- dependencias de liderazgo,
- relación con `ctx`,
- por qué una decisión de dispatch ocurre en ese punto.

**Riesgo**
- alto.

---

### `runtime/event_router.py`
**Dejar**
- routing y forwarding.

**Quitar**
- duplicidades,
- mezcla excesiva de red + persistencia + topología.

**Documentar**
- cuándo se reenvía,
- a quién se reenvía,
- qué pasa si no hay líder,
- cómo se evita duplicar o perder eventos.

**Riesgo**
- alto.

---

## Fase 5 — Final delicado

### `node/node_runtime.py`
**Dejar**
- estado vivo y operaciones nucleares del nodo.

**Quitar**
- llamadas HTTP directas si no son parte de su responsabilidad real.

**Documentar**
- qué representa el runtime,
- qué estado mantiene,
- qué puede mutar,
- qué módulos dependen de él.

**Riesgo**
- medio-alto.

---

### `runtime/context.py`
**Dejar**
- estado global mínimo imprescindible.

**Quitar**
- acceso directo disperso, pero al final del proceso.

**Documentar**
- variables globales expuestas,
- quién puede leerlas,
- quién puede mutarlas,
- por qué existen,
- riesgos de acoplamiento e imports circulares.

**Riesgo**
- muy alto.

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

## Plantilla obligatoria de cabecera por archivo

Usar algo como esto en cada archivo refactorizado:

```python
"""
<module_name>

Responsabilidad:
- Explica qué hace este archivo dentro del runtime.

Rol en la arquitectura:
- Explica cómo encaja en Mayhem y con qué módulos se relaciona.

Entradas principales:
- Qué datos recibe o consume.

Salidas / efectos laterales:
- Qué modifica, persiste, publica o devuelve.

Límites:
- Qué no debe hacer este módulo.

Notas de mantenimiento:
- Riesgos al modificarlo.
- Orden de inicialización si aplica.
- Dependencias sensibles si aplica.
"""
```

---

## Checklist obligatorio por archivo refactorizado

- estructura más limpia,
- comentarios exhaustivos añadidos,
- cabecera de módulo añadida,
- funciones críticas comentadas,
- zonas sensibles comentadas,
- smoke test OK,
- chaos corto si aplica.

---

## Siguiente paso recomendado

Siguiente movimiento:
1. terminar de sacar la API de `runtime/node_boot.py`,
2. documentar exhaustivamente cada archivo tocado,
3. dejar `node_boot.py` como ensamblador puro,
4. luego limpiar `event_log`, `leader` y `cluster_store`.
