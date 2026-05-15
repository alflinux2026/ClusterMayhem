# MAYHEM CLUSTER — SESSION PLAN (NEXT DAY)

# EOD STATUS — BASELINE

## Estado conseguido hoy

El cluster ya funciona como sistema distribuido básico operativo.

Actualmente:

* 3 nodos activos
* propagación HTTP funcional
* detección de caída funcional
* elección automática de líder funcional
* failover funcional
* convergencia de cluster funcional

El sistema YA se comporta como un cluster real simplificado.

---

# ESTADO ACTUAL DEL CLUSTER

## Arquitectura activa

### Networking

* FastAPI
* requests HTTP
* heartbeat broadcast
* endpoints `/cluster`
* endpoint `/leader`

---

## Componentes principales

### `NodeRuntime`

Responsable de:

* estado local
* transitions
* heartbeat payload
* lógica de liderazgo

---

### `ClusterWorker`

Loop principal:

```text
register_local_node()
emit_heartbeat()
sleep()
```

---

### `cluster_store`

Fuente de verdad compartida:

```python
cluster_state = {}
```

Con:

* TTL cleanup
* vista activa
* convergencia

---

### `transport/server.py`

Responsable de:

* recibir heartbeats
* exponer cluster state
* calcular líder

---

# VALIDACIONES CONSEGUIDAS

## TEST 1 — cluster convergence

Todos los nodos convergen a misma vista.

✔ OK

---

## TEST 2 — node expiration

Nodo muerto desaparece por TTL.

✔ OK

---

## TEST 3 — leader failover

Caída del líder:

```text
lnx200nas OFF
```

Nuevo líder:

```text
lnx202pc
```

✔ OK

---

## TEST 4 — leader recovery

Recuperación del nodo prioritario:

```text
lnx200nas ONLINE
```

Reasignación automática:

```text
leader -> lnx200nas
```

✔ OK

---

# PROBLEMAS ACTUALES

# 1. DOBLE FUENTE DE VERDAD

Actualmente existen:

```text
LeaseManager
cluster_state
```

Esto es incorrecto.

Puede generar:

* inconsistencias
* estados divergentes
* split-brain parcial

---

# DECISIÓN

Eliminar:

```text
LeaseManager
```

y usar únicamente:

```text
cluster_state + TTL
```

como fuente de verdad.

---

# 2. MUTACIONES DISTRIBUIDAS

Actualmente:

* workers escriben
* endpoints escriben
* varios puntos modifican estado

Riesgo:

```text
race conditions
```

---

# DECISIÓN

Centralizar escritura.

Único punto válido:

```text
POST /heartbeat
```

---

# 3. HACK TEMPORAL

Actualmente:

```python
BOOT == ACTIVE
```

en leader election.

Esto es incorrecto.

---

# DECISIÓN

Estados reales:

```text
BOOT
DISCOVERING
STANDBY
ACTIVE
DEGRADED
ISOLATED
OFFLINE
```

y sólo:

```text
ACTIVE
```

puede liderar.

---

# 4. LEADER ELECTION DEMASIADO SIMPLE

Actualmente:

```text
min(priority)
```

sin estabilidad temporal.

Puede oscilar.

---

# DECISIÓN

Introducir:

```text
leader stability window
```

Ejemplo:

```text
3 ciclos consecutivos
```

antes de confirmar cambio.

---

# 5. NO HAY THREAD SAFETY

`cluster_state` es memoria compartida sin locks.

Problema potencial:

* corrupción
* writes simultáneos
* lecturas inconsistentes

---

# DECISIÓN

Añadir:

```python
threading.Lock()
```

o estructura thread-safe.

---

# OBJETIVO PRINCIPAL DE MAÑANA

Convertir el cluster actual en:

```text
cluster determinista y estable
```

sin inconsistencias temporales.

---

# ROADMAP DE MAÑANA

# FASE 1 — CONSOLIDACIÓN DEL CLUSTER

## Objetivo

Eliminar incoherencias internas.

---

## Tareas

### 1. eliminar LeaseManager

Eliminar:

```text
lease/
lease_manager.py
```

Eliminar dependencias:

* NodeRuntime
* ElectionEngine
* HeartbeatWorker

---

### 2. cluster_state como única verdad

TODO el cluster depende exclusivamente de:

```python
get_active_cluster()
```

---

### 3. centralizar escrituras

Único punto de mutación:

```python
POST /heartbeat
```

Workers NO deben mutar directamente.

---

### 4. compute_leader único

Actualmente duplicado.

Unificar en:

```text
cluster/runtime/leader.py
```

---

### 5. limpiar estados

Eliminar:

```text
BOOT == ACTIVE
```

Definir flujo real:

```text
BOOT
 -> DISCOVERING
 -> STANDBY
 -> ACTIVE
```

---

# FASE 2 — ESTABILIDAD

## Objetivo

Evitar oscilaciones.

---

## Tareas

### stability window

Ejemplo:

```text
candidate must survive 3 cycles
```

antes de convertirse en líder.

---

### cooldown opcional

Evitar:

```text
leader bouncing
```

---

# FASE 3 — DATA PLANE INICIAL

## Objetivo

Primer sistema distribuido de datos real.

---

# PRUEBA "DATATEST"

## Idea

Sólo el líder puede generar datos válidos.

Cada X segundos:

```json
{
  "timestamp": "...",
  "leader": "lnx200nas",
  "counter": 1822
}
```

---

# Objetivos de validación

## Validar:

* continuidad de secuencia
* pérdida de datos
* failover limpio
* recuperación de líder
* ordering global
* convergencia

---

# FORMATO PROPUESTO

## JSONL append-only

```text
cluster_data/
  wal/
    2026-05-15/
      wal-000001.log
```

Eventos:

```json
{"seq":1,"leader":"lnx200nas"}
{"seq":2,"leader":"lnx200nas"}
```

---

# REPLICACIÓN (FASE FUTURA)

## Modelo previsto

```text
leader
   |
   +--> append local WAL
   +--> replicate followers
   +--> quorum ACK
   +--> COMMIT
```

---

# CONCEPTO CLAVE

El cluster ya tiene:

```text
CONTROL PLANE
```

Ahora empieza:

```text
DATA PLANE
```

es decir:

* persistencia real
* WAL
* replicación
* ordering
* commit
* recovery

---

# OBJETIVO FINAL DEL DÍA

Al terminar mañana:

✔ cluster consistente
✔ 1 líder estable
✔ failover limpio
✔ convergencia determinista
✔ sin doble fuente de verdad
✔ base lista para WAL distribuido
✔ primer test de datos reales operativo

---

# PRIORIDAD REAL

## IMPORTANTE

NO intentar mañana:

* Raft completo
* quorum complejo
* sharding
* consensus avanzado

---

# PRIORIDAD CORRECTA

Primero:

```text
cluster simple
estable
determinista
predecible
```

Después:

```text
data replication
WAL
consensus
```

---

# ESTADO DEL PROYECTO

Actualmente el proyecto ya pasó de:

```text
toy heartbeat demo
```

a:

```text
cluster distribuido funcional básico
```

El siguiente salto es:

```text
distributed replicated data system
```

que ya es arquitectura distribuida real.
