# Máquina de estados de nodo

## Objetivo

Definir una máquina de estados de nodo más precisa que la actual, separando claramente:

- comandos externos,
- comandos automáticos,
- estados reales del nodo,
- pipeline funcional por estado,
- salidas controladas frente a salidas bruscas.

La implementación actual hace transiciones demasiado directas:

- `BOOT -> STANDBY`
- `STANDBY <-> ACTIVE` según `compute_leader()`
- `/sleep -> ISOLATED`
- `/revive -> STANDBY`

Eso es útil para el MVP, pero mezcla casos distintos:

- arranque con trabajo pendiente,
- pérdida ordenada de liderazgo,
- descanso controlado,
- aislamiento suave,
- muerte brusca simulada.

---

## Convención

- Elementos **entre paréntesis**: **comandos**.
- Elementos **sin paréntesis**: **estados**.

Ejemplos:

- `(SLEEP)`, `(WAKEUP)`, `(ISOLATE_SOFT)`, `(ISOLATE_HARD)` = comandos externos.
- `(LEADER_SEL_UP)`, `(LEADER_SEL_DOWN)` = comandos automáticos.
- `BOOT`, `DRAIN_TO_STANDBY`, `ACTIVE`, `STANDBY`, `DRAIN_TO_SLEEP`, `SLEEPING`, `DRAIN_TO_ISOLATE`, `ISOLATED` = estados.

---

## Principio de diseño

Primero cerrar ventana.  
Después limpiar mesa.  
Y solo al final alcanzar el estado destino.

Ese principio aplica a todas las salidas controladas:

- hacia `STANDBY`,
- hacia `SLEEPING`,
- hacia `ISOLATED` por ruta suave.

La única excepción es el aislamiento duro:

- `(ISOLATE_HARD) -> ISOLATED`

---

## Estados propuestos

## `BOOT`

Estado inicial del nodo al arrancar.

Responsabilidades:

- inicialización,
- inspección de journal local,
- detección de trabajo pendiente,
- decisión de entrada ordenada a operación.

No debería asumir automáticamente que puede pasar siempre a `STANDBY`.

---

## `DRAIN_TO_STANDBY`

Estado transitorio de drenado con destino `STANDBY`.

Uso:

- arranque con pendientes,
- pérdida ordenada de liderazgo,
- salida controlada a modo follower disponible.

Semántica:

- deja de abrir trabajo nuevo como líder,
- completa housekeeping,
- termina obligatoriamente en `STANDBY`.

---

## `STANDBY`

Nodo sano, vivo, integrado en clúster, no líder.

Características:

- puede enviar heartbeat;
- puede ser elegible para liderazgo;
- puede recibir comandos de sleep o isolate;
- no debe operar como líder.

---

## `ACTIVE`

Nodo líder operativo.

Características:

- liderazgo efectivo;
- operación normal de líder;
- si deja de ser líder, no cae en seco a `STANDBY`, sino que pasa por `DRAIN_TO_STANDBY`.

---

## `DRAIN_TO_SLEEP`

Estado transitorio de drenado con destino `SLEEPING`.

Uso:

- descanso controlado,
- mantenimiento ligero,
- rotación intencional de líder.

Semántica:

- salida ordenada;
- no cambia de destino a mitad;
- termina obligatoriamente en `SLEEPING`.

---

## `SLEEPING`

Nodo fuera de operación por decisión controlada.

Características:

- no participa en liderazgo;
- no debería aceptar trabajo nuevo;
- puede volver con `(WAKEUP) -> STANDBY`.

---

## `DRAIN_TO_ISOLATE`

Estado transitorio de drenado con destino `ISOLATED`.

Uso:

- aislamiento suave,
- salida ordenada del clúster con intención de quedar aislado al final.

Semántica:

- cierre controlado,
- limpieza previa,
- termina obligatoriamente en `ISOLATED`.

---

## `ISOLATED`

Nodo fuera de clúster.

Importante:

- puede alcanzarse por ruta suave o por ruta dura,
- pero el estado final es el mismo.

Diferencia:

- si llega por `(ISOLATE_SOFT)`, hubo drenado;
- si llega por `(ISOLATE_HARD)`, no lo hubo.

La implementación actual ya usa `ISOLATED` como estado fuera de operación.

---

## Comandos

## Comandos externos

### `(SLEEP)`

Orden de descanso controlado.

No significa “duérmete ya”.  
Significa: iniciar secuencia ordenada hacia `SLEEPING`.

Transiciones:

- `ACTIVE -> DRAIN_TO_SLEEP`
- `STANDBY -> DRAIN_TO_SLEEP`

---

### `(WAKEUP)`

Orden de reentrada al clúster.

Transiciones:

- `SLEEPING -> STANDBY`
- `ISOLATED -> STANDBY`

---

### `(ISOLATE_SOFT)`

Orden de aislamiento suave.

No significa “cae ya”.  
Significa: iniciar secuencia ordenada hacia aislamiento final.

Transiciones:

- `ACTIVE -> DRAIN_TO_ISOLATE`
- `STANDBY -> DRAIN_TO_ISOLATE`

---

### `(ISOLATE_HARD)`

Orden de aislamiento brusco.

Representa:

- chaos,
- muerte brusca simulada,
- corte inmediato.

Transición:

- `ANY -> ISOLATED`

---

## Comandos automáticos

### `(LEADER_SEL_UP)`

Comando interno emitido cuando el nodo en `STANDBY` pasa a ser el líder seleccionado.

Transición:

- `STANDBY -> ACTIVE`

---

### `(LEADER_SEL_DOWN)`

Comando interno emitido cuando el nodo en `ACTIVE` deja de ser el líder seleccionado.

Transición:

- `ACTIVE -> DRAIN_TO_STANDBY`

No debe hacer `ACTIVE -> STANDBY` directo.

---

## Pipeline por estado

### `BOOT`

Orden funcional:

1. `load_context()`
2. `load_persistent_state()`
3. `inspect_local_journal()`
4. `detect_pending_work()`
5. `decide_initial_transition()`
6. `start_background_loops_if_needed()`

Funciones que se apagan al salir de `BOOT`:

- la lógica de inicialización no debe repetirse;
- el estado deja de decidir arranque y pasa a ejecutar operación normal.

---

### `DRAIN_TO_STANDBY`

Orden funcional:

1. `emit_heartbeat()`
2. `stop_leader_dispatch()`
3. `stop_new_work_acceptance()`
4. `flush_pending_events()`
5. `generate_last_append_if_needed()`
6. `replicate_if_dirty()`
7. `clear_working_flag()`
8. `finalize_transition_to_standby()`

Funciones que se apagan al entrar aquí:

- `dispatch_tick()`,
- `handle_work_queue()` como productor de trabajo nuevo,
- cualquier acción que abra nueva ventana de trabajo.

---

### `STANDBY`

Orden funcional:

1. `emit_heartbeat()`
2. `accept_control_commands()`
3. `participate_in_leader_election()`
4. `monitor_cluster_state()`
5. `handle_work_queue()` si aplica como housekeeping no líder
6. `reconcile_tick()` solo si es necesario para limpieza local
7. `generate_last_append_if_needed()`
8. `replicate_if_dirty()`
9. `prepare_for_promotion()`

Funciones que se apagan en `STANDBY`:

- `dispatch_tick()` como líder,
- `check_leadership()` como acción de liderazgo efectivo,
- cualquier función que asuma autoridad de líder.

---

### `ACTIVE`

Orden funcional:

1. `emit_heartbeat()`
2. `dispatch_tick()`
3. `handle_work_queue()`
4. `reconcile_tick()`
5. `generate_last_append_if_needed()`
6. `replicate_if_dirty()`
7. `check_leadership()`

Notas:

- `emit_heartbeat()` tiene prioridad alta y se ejecuta en todos los estados permitidos.
- `generate_last_append_if_needed()` es el punto que puede levantar `last_append.state.json`.
- `replicate_if_dirty()` solo reacciona al append pendiente, no al estado del nodo ni a `mtime`.

Funciones que se apagan al salir de `ACTIVE`:

- `dispatch_tick()` deja de actuar como líder;
- `handle_work_queue()` deja de producir nueva carga líder;
- `check_leadership()` deja de mantener autoridad y pasa a transición.

---

### `DRAIN_TO_SLEEP`

Orden funcional:

1. `emit_heartbeat()`
2. `stop_new_work_acceptance()`
3. `flush_pending_events()`
4. `generate_last_append_if_needed()`
5. `replicate_if_dirty()`
6. `clear_working_flag()`
7. `finalize_transition_to_sleeping()`

Funciones que se apagan al entrar aquí:

- `dispatch_tick()`,
- `reconcile_tick()` salvo limpieza de cierre si fuera imprescindible,
- cualquier generación de nuevo trabajo.

---

### `SLEEPING`

Orden funcional:

1. `accept_wakeup_command()`
2. `reject_work_and_leadership()`
3. `stay_quiet()`
4. `prepare_rejoin_state()`

Funciones que se apagan en `SLEEPING`:

- `emit_heartbeat()`,
- `dispatch_tick()`,
- `reconcile_tick()`,
- `replicate_if_dirty()`,
- `check_leadership()`,
- `handle_work_queue()`.

---

### `DRAIN_TO_ISOLATE`

Orden funcional:

1. `emit_heartbeat()`
2. `stop_new_work_acceptance()`
3. `flush_pending_events()`
4. `generate_last_append_if_needed()`
5. `replicate_if_dirty()`
6. `clear_working_flag()`
7. `finalize_transition_to_isolated()`

Funciones que se apagan al entrar aquí:

- `dispatch_tick()`,
- `reconcile_tick()` como producción normal,
- cualquier acción que mantenga al nodo como miembro operativo.

---

### `ISOLATED`

Orden funcional:

1. `reject_cluster_participation()`
2. `stop_heartbeat()`
3. `stop_dispatch()`
4. `stop_reconcile()`
5. `stop_replication()`
6. `accept_wakeup_command()`

Funciones que se apagan en `ISOLATED`:

- todo el pipeline operativo;
- cualquier actividad de liderazgo;
- cualquier replicación automática;
- cualquier trabajo nuevo.

---

## Comandos y transiciones

## Arranque

### Arranque con pendientes

`BOOT -> DRAIN_TO_STANDBY -> STANDBY`

### Arranque limpio

Opción uniforme recomendada:

`BOOT -> DRAIN_TO_STANDBY -> STANDBY`

La implementación actual usa la opción simplificada `BOOT -> STANDBY`, pero la máquina propuesta normaliza el arranque para pasar por drenado.

---

## Liderazgo

### Promoción

`STANDBY -> (LEADER_SEL_UP) -> ACTIVE`

### Pérdida de liderazgo

`ACTIVE -> (LEADER_SEL_DOWN) -> DRAIN_TO_STANDBY -> STANDBY`

---

## Descanso controlado

### Desde líder

`ACTIVE -> (SLEEP) -> DRAIN_TO_SLEEP -> SLEEPING`

### Desde follower

`STANDBY -> (SLEEP) -> DRAIN_TO_SLEEP -> SLEEPING`

### Reentrada

`SLEEPING -> (WAKEUP) -> STANDBY`

---

## Aislamiento suave

### Desde líder

`ACTIVE -> (ISOLATE_SOFT) -> DRAIN_TO_ISOLATE -> ISOLATED`

### Desde follower

`STANDBY -> (ISOLATE_SOFT) -> DRAIN_TO_ISOLATE -> ISOLATED`

### Reentrada

`ISOLATED -> (WAKEUP) -> STANDBY`

---

## Aislamiento duro

### Desde cualquier estado

`ANY -> (ISOLATE_HARD) -> ISOLATED`

### Reentrada

`ISOLATED -> (WAKEUP) -> STANDBY`

---

## Tabla resumida

| Estado actual | Comando | Estado siguiente | Observación |
|---|---|---|---|
| `BOOT` | automático | `DRAIN_TO_STANDBY` o `STANDBY` | Según haya pendientes o no. |
| `STANDBY` | `(LEADER_SEL_UP)` | `ACTIVE` | Promoción a líder. |
| `ACTIVE` | `(LEADER_SEL_DOWN)` | `DRAIN_TO_STANDBY` | Pérdida ordenada de liderazgo. |
| `DRAIN_TO_STANDBY` | automático fin de secuencia | `STANDBY` | Secuencia cerrada. |
| `ACTIVE` | `(SLEEP)` | `DRAIN_TO_SLEEP` | Descanso controlado. |
| `STANDBY` | `(SLEEP)` | `DRAIN_TO_SLEEP` | Descanso controlado. |
| `DRAIN_TO_SLEEP` | automático fin de secuencia | `SLEEPING` | Secuencia cerrada. |
| `SLEEPING` | `(WAKEUP)` | `STANDBY` | Reentrada limpia. |
| `ACTIVE` | `(ISOLATE_SOFT)` | `DRAIN_TO_ISOLATE` | Aislamiento ordenado. |
| `STANDBY` | `(ISOLATE_SOFT)` | `DRAIN_TO_ISOLATE` | Aislamiento ordenado. |
| `DRAIN_TO_ISOLATE` | automático fin de secuencia | `ISOLATED` | Secuencia cerrada. |
| `ANY` | `(ISOLATE_HARD)` | `ISOLATED` | Corte brusco. |
| `ISOLATED` | `(WAKEUP)` | `STANDBY` | Reentrada tras aislamiento. |

---

## Restricciones

## No válidas

Estas transiciones no deberían permitirse:

- `ACTIVE -> STANDBY` directo por pérdida de liderazgo.
- `ACTIVE -> SLEEPING` directo.
- `ACTIVE -> ISOLATED` directo salvo por `(ISOLATE_HARD)`.
- `DRAIN_TO_STANDBY -> ACTIVE` por comando normal.
- `DRAIN_TO_SLEEP -> STANDBY` por comando normal.
- `DRAIN_TO_ISOLATE -> STANDBY` por comando normal.

## Válida como override duro

- `DRAIN_TO_* -> (ISOLATE_HARD) -> ISOLATED`

---

## Impacto en implementación

## Lo que hace hoy el código

Actualmente:

- `tick()` hace `BOOT -> STANDBY`;
- `tick()` hace `STANDBY <-> ACTIVE` de forma directa según `compute_leader()`;
- `/sleep` fuerza `ISOLATED`;
- `/revive` fuerza `STANDBY`;
- `ISOLATED` corta heartbeat, dispatch, replication y reconcile en el loop.

## Lo que habría que cambiar

1. Ampliar `NodeState` con:
   - `DRAIN_TO_STANDBY`
   - `DRAIN_TO_SLEEP`
   - `DRAIN_TO_ISOLATE`
   - `SLEEPING`

2. Separar endpoints/comandos:
   - `/sleep` => `(SLEEP)`
   - `/isolate-soft` => `(ISOLATE_SOFT)`
   - `/isolate-hard` => `(ISOLATE_HARD)`
   - `/wakeup` => `(WAKEUP)`

3. Hacer que `tick()` emita comandos automáticos:
   - `(LEADER_SEL_UP)`
   - `(LEADER_SEL_DOWN)`

4. Implementar lógica automática de finalización para cada `DRAIN_TO_*`.

5. Decidir qué subsistemas siguen activos en cada `DRAIN_TO_*`:
   - heartbeat,
   - dispatch,
   - reconcile,
   - log replication.

---

## Notas sobre apagado secuencial de funciones

Las funciones no se desactivan todas a la vez.

Se apagan de forma secuencial según el estado:

- primero se corta la apertura de trabajo nuevo,
- luego se vacía la mesa de trabajo,
- luego se replica el último append si existe,
- después se limpia la bandera de dirty,
- y finalmente se alcanza el estado estable destino.

Eso evita:

- pérdidas de trabajo,
- cambios de intención a mitad,
- duplicidad de appends,
- y réplicas espurias.

---

## Preguntas abiertas para futura iteración

- ¿`BOOT` debe pasar siempre por `DRAIN_TO_STANDBY`?
- ¿Qué condición exacta define “fin de drenado”?
- ¿`DRAIN_TO_SLEEP` mantiene heartbeat?
- ¿`DRAIN_TO_ISOLATE` replica una última vez antes de aislarse?
- ¿`ISOLATE_HARD` debe interrumpir cualquier estado sin excepción?
- ¿Hace falta persistir la causa de entrada en `ISOLATED` o basta con el comando recibido?

---

## Resumen de criterio

- `STANDBY` = vivo y disponible, no líder.
- `ACTIVE` = líder operativo.
- `SLEEPING` = fuera por decisión controlada.
- `ISOLATED` = fuera de clúster, por ruta suave o dura.
- `DRAIN_TO_*` = estados transitorios con destino explícito.
- Los comandos expresan intención.
- Los estados expresan condición real del nodo.
- Las transiciones automáticas las resuelve el runtime.
- La réplica no depende del estado en sí, sino de si algún proceso del estado ha generado un nuevo append.
