Aquí tienes el **Session Boot + documentación limpia del estado real del sistema**, y luego el artefacto que pediste.

---

## 🧭 SESSION BOOT (CLUSTER REAL STATE)

### Estado actual del sistema

Tienes ya un sistema que ha pasado de:

* simulador manual
* scripts sueltos
* tests ad-hoc

a:

👉 **cluster runtime funcional + chaos testing + invariants loop**

---

### 🧠 Qué YA es “real” (no experimental)

Estos módulos ya forman parte del **core del sistema real**:

#### 🧱 Runtime del cluster

* `cluster/node/node_runtime.py` → ciclo de vida del nodo
* `cluster/runtime/state.py` → estados del cluster
* `cluster/runtime/cluster_view.py` → visión local del cluster

#### 🗳️ Elección y autoridad

* `cluster/election/election_engine.py`
* `cluster/election/leader.py`
* `cluster/lease/lease_manager.py`
* `cluster/lease/lease.py`

#### 🔁 Self-healing base

* `cluster/workers/heartbeat_worker.py`
* `cluster/workers/lease_worker.py`

#### 🧪 Invariantes + chaos

* `testing/invariants.py`
* `testing/chaos_engine.py`
* `scripts/chaos_cluster_runner.py`

#### 📡 Dataset + replication (base)

* `cluster/datasets/*`
* `cluster/replication/*`

---

### ⚠️ Qué todavía NO es producción

Esto sigue siendo “experimental controlado”:

* tolerancia a fallos real en red (parcial)
* persistencia fuerte (WAL / fsync real)
* multi-host real (aún no validado en LAN real)
* seguridad de split-brain en red real (solo simulada)
* clock drift real (no modelado aún)

---

### 🧪 Qué YA puedes hacer ahora mismo

✔ simular cluster 3 nodos
✔ matar nodos
✔ inducir delays
✔ provocar split-brain
✔ validar invariants
✔ auto-reelección básica
✔ lease expiration real (TTL)

---

### 🚀 Siguiente salto lógico (IMPORTANTE)

Ahora hay 2 caminos posibles:

#### 1. 🧪 HARDENING (recomendado)

* convertir runtime en daemon real por máquina
* sockets / HTTP entre nodos reales
* heartbeat real over network
* lease distribuido real

#### 2. 🧩 CONSOLIDACIÓN (más seguro)

* unificar APIs duplicadas
* eliminar simuladores redundantes
* estabilizar interfaces de core
* cerrar contratos definitivos

---

## 📌 CLUSTER RUNTIME CONTRACT (DOCUMENTO)

Aquí tienes el documento formal encapsulado:

````markdown
# Cluster Runtime Contract

## Version
0.1.0

## Scope

Este contrato define el comportamiento obligatorio de un nodo
en runtime dentro del cluster mayhem.

Aplica a:

- ejecución local del nodo
- interacción con peers
- gestión de estado
- participación en liderazgo
- validación de lease
- reacción a fallos

---

# 1. PRINCIPIO FUNDAMENTAL

Cada nodo es autónomo.

Pero ningún nodo es soberano.

La autoridad es siempre derivada del cluster.

---

# 2. CICLO DE VIDA DEL NODO

Un nodo SIEMPRE ejecuta este loop:

```text
tick()
  ├── validar lease
  ├── evaluar estado actual
  ├── actualizar heartbeat
  ├── evaluar liderazgo
  ├── ejecutar transición de estado
  └── sincronizar cluster view
````

Este loop es obligatorio y continuo.

---

# 3. RESPONSABILIDADES POR ESTADO

## BOOT

* inicializar runtime
* cargar config
* no participar en cluster

## DISCOVERING

* descubrir peers
* construir cluster view
* validar lease existente

## STANDBY

* replicar datos
* monitorizar ACTIVE
* estar listo para takeover
* NO escribir

## ACTIVE

* único escritor válido
* emite heartbeat
* mantiene lease
* coordina cluster

## DEGRADED

* no puede liderar
* evita decisiones críticas
* espera recuperación o reelección

## ISOLATED

* no confía en cluster view
* no participa en elecciones

## OFFLINE

* nodo fuera del cluster

---

# 4. REGLA DE AUTORIDAD

Solo un nodo puede ser ACTIVE.

Si existen múltiples ACTIVE:

→ se activa resolución de split-brain
→ el nodo de menor prioridad gana
→ el resto se degrada

---

# 5. LEASE CONTRACT

* ACTIVE debe mantener lease válido
* lease expira → pérdida de autoridad
* lease inválido → degradación inmediata

---

# 6. HEARTBEAT CONTRACT

* ACTIVE emite heartbeat constante
* STANDBY escucha heartbeat
* ausencia de heartbeat → sospecha de fallo

---

# 7. SELF-HEAL LOOP

El cluster se repara mediante:

```text
heartbeat tick
→ detectar fallo
→ invalidar lease
→ reevaluar liderazgo
→ promover nuevo ACTIVE
→ estabilizar cluster
```

---

# 8. INVARIANTES

Estos invariantes NUNCA pueden romperse:

* máximo 1 ACTIVE
* STANDBY nunca escribe
* OFFLINE no participa
* lease siempre pertenece a ACTIVE
* decisiones deben ser deterministas

---

# 9. CONSISTENCIA

El sistema prioriza:

1. seguridad
2. consistencia
3. disponibilidad

Nunca al revés.

---

# 10. OBJETIVO FINAL

Cluster capaz de:

* sobrevivir fallos arbitrarios
* mantener 1 líder estable
* recuperarse automáticamente
* resistir particiones de red

```

---

## 🧩 Qué deberías guardar ya (BACKUP IMPORTANTE)

Esto YA es núcleo del sistema:

📦 guardar como “core stable”:

- `node_runtime.py`
- `lease_manager.py`
- `election_engine.py`
- `heartbeat_worker.py`
- `runtime/state.py`
- `testing/invariants.py`
- `testing/chaos_engine.py`
- `scripts/chaos_cluster_runner.py`
- `docs/cluster-state-machine.md`
- ESTE nuevo:
  - `docs/cluster_runtime_contract.md`

---

## 🧭 Siguiente paso real (sin caos innecesario)

Si quieres avanzar de verdad al siguiente nivel:

👉 el próximo paso NO es más código  
👉 es elegir uno:

### A. “REAL NETWORK MODE”
3 procesos en 3 máquinas reales (SSH + sockets)

### B. “STABILIZATION MODE”
limpiar + congelar API interna + eliminar duplicaciones

---

Si quieres, mañana podemos dar el salto grande:

👉 convertir esto en un **mini-RAFT funcional en LAN real (sin librerías externas)**
```
