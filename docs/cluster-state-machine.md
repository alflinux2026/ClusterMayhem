# File: docs/cluster-state-machine.md
# Previous: none
# Author: alftorres
# Date: 2026-05-13T16:02:00+0200
# Version: 0.1.0
# Genealogy:
#   docs/cluster-state-machine.md 0.1.0 2026-05-13T16:02:00+0200
#   God
#
# Purpose:
#   Define valid cluster node states and legal transitions.
#
# FRV-ID: 0c7b3f9e7d1a0d91
# Header_End

```markdown
# File: docs/cluster-state-machine.md
# Proyecto: mayhem-cluster
# Documento: cluster-state-machine
# Versión: 0.1.0
# Estado: borrador

# 1. OBJETIVO

Definir:

- estados válidos de los nodos
- transiciones permitidas
- condiciones de activación
- degradación
- recuperación
- failover
- prevención de split brain

Este documento es normativo.

La implementación debe obedecer esta máquina de estados.

---

# 2. PRINCIPIOS

## 2.1 Determinismo

Dado el mismo estado observable del cluster:

todos los nodos deben llegar a la misma decisión.

---

## 2.2 Autoridad temporal

La autoridad del nodo activo:

no es permanente.

Depende de:

- salud
- lease
- prioridad
- conectividad
- consistencia

---

## 2.3 Seguridad antes que disponibilidad

Ante duda:

preferir STANDBY antes que doble ACTIVE.

---

# 3. ESTADOS VÁLIDOS

## BOOT

Estado inicial. Nodo arrancando.

Características:

- configuración cargando
- datasets no validados
- watchdog aún no iniciado
- peers desconocidos

Restricción:
- no puede servir tráfico

---

## DISCOVERING

Nodo explorando el cluster.

Responsabilidades:

- cargar peers
- consultar health
- detectar líder
- validar leases
- construir cluster view

---

## STANDBY

Nodo sano preparado para takeover.

Responsabilidades:

- replicar datasets
- monitorizar activo
- mantener snapshots
- renovar estado local del cluster

Restricción:
- no acepta escrituras

---

## ACTIVE

Nodo líder actual.

Responsabilidades:

- aceptar escrituras
- coordinar datasets
- renovar lease
- publicar estado oficial
- servir tráfico

Restricción:
- máximo un ACTIVE

---

## DEGRADED

Nodo parcialmente operativo.

Ejemplos:

- datasets corruptos
- lease inválido
- inconsistencias
- pérdida parcial de conectividad

Restricción:
- no puede asumir liderazgo

---

## ISOLATED

Nodo aislado de peers.

Puede ocurrir por:

- corte de red
- VPN caída
- WiFi inestable
- pérdida de routing

Política:
- no promover automáticamente si existe duda de quorum

---

## OFFLINE

Nodo no operativo.

Causas posibles:

- apagado
- crash
- watchdog muerto
- proceso detenido

---

# 4. TRANSICIONES

## BOOT → DISCOVERING

Condiciones:

- config válida
- runtime inicializado
- watchdog arrancado

---

## DISCOVERING → STANDBY

Condiciones:

- líder válido detectado
- datasets sincronizados
- lease remoto válido

---

## DISCOVERING → ACTIVE

Condiciones:

- no existe líder válido
- nodo con mayor prioridad sana
- datasets válidos
- lease adquirible

---

## STANDBY → ACTIVE

Condiciones:

- lease del líder expirado
- líder no alcanzable
- nodo elegible
- prioridad suficiente
- datasets consistentes

---

## ACTIVE → STANDBY

Condiciones:

- aparece nodo superior sano
- lease perdido
- conflicto detectado
- prioridad inferior
- takeover remoto válido

Transición obligatoria inmediata.

---

## ACTIVE → DEGRADED

Condiciones:

- corrupción detectada
- datasets inválidos
- errores internos críticos
- watchdog inconsistente

---

## DEGRADED → STANDBY

Condiciones:

- recuperación completa
- datasets válidos
- watchdog estable

---

## CUALQUIER ESTADO → OFFLINE

Condiciones:

- proceso detenido
- error fatal
- shutdown explícito

---

## CUALQUIER ESTADO → ISOLATED

Condiciones:

- pérdida total de peers
- routing roto
- VPN caída
- timeout global

---

## ISOLATED → DISCOVERING

Condiciones:

- conectividad restaurada

---

# 5. ELECCIÓN DE LÍDER

Regla principal:

El líder será el nodo sano con menor priority.

---

## Requisitos para ACTIVE

- watchdog válido
- datasets íntegros
- lease válido
- sin líder superior visible
- sincronización suficiente

---

## Restricción de seguridad

Si existen dudas sobre autoridad:

NO asumir ACTIVE.

---

# 6. LEASE STATE

## VALID
Lease vigente.

## EXPIRED
Lease caducado. El nodo pierde autoridad.

## UNKNOWN
Estado no verificable.

Política general:
- preferir STANDBY ante incertidumbre

---

# 7. SPLIT BRAIN

## Detección

Existe split brain si:

- más de un ACTIVE simultáneo

---

## Resolución

Reglas:

- menor priority gana
- lease más reciente gana
- empate → menor node_id gana

El nodo perdedor:

debe degradarse inmediatamente a STANDBY.

---

# 8. CLUSTER VIEW

Cada nodo mantiene una `cluster_view` local:

Incluye:

- peers conocidos
- health
- lease status
- active node
- latencias
- datasets
- timestamps

Importante:

- la cluster_view es local
- no existe memoria global centralizada

---

# 9. INVARIANTES

## Invariante 1
Máximo un ACTIVE válido.

## Invariante 2
Solo ACTIVE acepta escrituras.

## Invariante 3
Todos los nodos ejecutan el mismo código.

## Invariante 4
Todo ACTIVE debe poseer lease válido.

## Invariante 5
STANDBY nunca debe publicar autoridad.

---

# 10. FILOSOFÍA OPERATIVA

El cluster está diseñado para:

- LAN doméstica
- hardware heterogéneo
- apagados arbitrarios
- reconexión automática
- nodos intermitentes
- mínima complejidad externa

---

# 11. OBJETIVO FASE 1

Estado objetivo inicial:

- 3 nodos
- 1 líder
- failover automático
- sin split brain
- replicación pull
- datasets JSON

---

# 12. FUTURAS EXTENSIONES

Posibles evoluciones:

- quorum real
- RAFT-lite
- WAL distribuido
- snapshots incrementales
- WebSocket replication
- CRDT datasets
```

```
```
