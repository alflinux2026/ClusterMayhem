# CLUSTER PROJECT — STATUS ACTUAL

## 1. Estado general
- Cluster distribuido funcional con 3 nodos.
- Comunicación por HTTP (FastAPI + requests).
- Heartbeats operativos.
- Vista de cluster sincronizada entre nodos.
- Elección de líder funcionando por prioridad (menor gana).
- TTL básico para expiración de nodos.

## 2. Arquitectura actual

### Componentes activos
- `NodeRuntime` → estado del nodo + lógica de transición
- `ClusterWorker` → loop de heartbeat + registro local
- `transport/server.py` → API HTTP central del nodo
- `transport/client.py` → envío de heartbeats
- `cluster_store` → estado compartido en memoria
- `LeaseManager` → control de “líder activo”
- `ElectionEngine` → gating simple de elección

## 3. Flujo actual

1. Nodo arranca (`run_node`)
2. Se registra en `cluster_state`
3. Worker entra en loop:
   - registra self
   - envía heartbeat a peers
4. Servidores reciben heartbeat → actualizan `cluster_state`
5. `/cluster` devuelve vista filtrada por TTL
6. `/leader` calcula líder global

## 4. Estado real del sistema

### Funciona
- Propagación de estado entre nodos
- Consenso básico de líder
- Expiración de nodos caídos (TTL)
- Failover cuando un nodo desaparece

### Ya corregido
- Eliminación de acceso directo inconsistente a `cluster_state` en lectura
- Uso de `get_active_cluster()` como fuente única
- Limpieza centralizada (`cleanup_cluster`)

## 5. Problemas actuales (no resueltos)

- LeaseManager es redundante con cluster_state (doble fuente de verdad)
- No hay anti-split-brain real (solo TTL + priority)
- ElectionEngine demasiado trivial
- No hay quorum
- Heartbeat no valida consistencia de líder
- Estado BOOT se usa como ACTIVE en leader calc (temporal hack)

## 6. Riesgos actuales

- Split-brain si TTL se desincroniza
- Líder puede “resucitar” sin consenso real
- Race conditions en cluster_state (memoria compartida sin locks)
- Dependencia fuerte de timing (sleep-based system)

## 7. Estado del objetivo

✔ Cluster básico funcional  
❌ Sistema distribuido robusto (aún no)  
⚠️ Requiere capa de consenso real (Raft-lite o mejora de lease)

---

# SESSION BOOT — MAÑANA

## Objetivo de la sesión
Convertir el cluster actual en un sistema coherente de **liderazgo estable sin inconsistencias temporales**.

---

## 1. Fix prioritario (OBLIGATORIO)

Eliminar doble sistema:
- ❌ LeaseManager como fuente de verdad
- ❌ cluster_state + lease duplicados

👉 Unificar en:
- `cluster_state` + TTL + heartbeat

---

## 2. Mejoras de consistencia

- Introducir lock o estructura thread-safe en cluster_state
- Asegurar orden único de escritura:
  - solo `/heartbeat` escribe estado
  - workers NO deben mutar cluster_state directamente

---

## 3. Elección de líder (upgrade mínimo)

Sustituir lógica actual por:

- Filtrar nodos activos (TTL)
- Elegir menor priority
- Validar estabilidad (2–3 ciclos consecutivos)

---

## 4. Eliminación de hacks actuales

- BOOT != ACTIVE en leader logic
- logs de debugging globales
- duplicación de compute_leader (server vs node_boot)

---

## 5. Refactor mínimo recomendado

- 1 sola función `compute_leader()` global
- 1 solo módulo de estado (cluster_store)
- 1 flujo de escritura (heartbeat)

---

## 6. Meta de la sesión

Al final del día:

✔ 1 líder estable  
✔ sin oscilación entre nodos  
✔ sin inconsistencias entre endpoints  
✔ cluster determinista bajo fallo de nodos  

---

FIN DEL DOCUMENTO
