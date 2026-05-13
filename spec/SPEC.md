# File: spec/SPEC.md
# Previous: none
# Author: alftorres
# Date: 2026-05-13T15:01:54+0200
# Version: 0.0.0
# Genealogy:
#   spec/SPEC.md 0.0.0 2026-05-13T15:01:54+0200
#   God
#
# Purpose:
# Notes:
#
# FRV-ID: 37847ccc6a46ebeb
# Header_End

# `mayhem-cluster`

## Contrato funcional inicial del sistema

```text
Project: mayhem-cluster
Version: 0.1.0
Status: draft
Type: distributed failover cluster
Scope: LAN autonomous cluster coordination
```

---

# 1. OBJETIVO

`mayhem-cluster` es un núcleo de coordinación distribuida para servicios LAN.

Su responsabilidad es:

* descubrir nodos,
* vigilar salud,
* elegir nodo activo,
* coordinar failover,
* replicar datasets,
* mantener consistencia operativa,
* exponer estado común del cluster.

No implementa lógica de aplicación.

Las aplicaciones externas consumen el estado del cluster.

---

# 2. PRINCIPIOS FUNDAMENTALES

## 2.1 Código único

Todos los nodos ejecutan exactamente el mismo código.

No existen:

* binarios primarios,
* binarios backup,
* builds especiales.

La diferencia de comportamiento depende únicamente del estado del cluster.

---

## 2.2 Un único nodo activo

En cada instante:

```text
máximo 1 nodo activo
```

El resto:

* standby,
* observer,
* offline,
* degraded.

---

## 2.3 Prioridad determinista

La elección del nodo activo depende de:

1. salud real,
2. prioridad numérica,
3. watchdog válido,
4. lease vigente.

---

## 2.4 Cluster autónomo

Cada nodo:

* mantiene copia local del estado,
* evalúa a los demás,
* puede asumir liderazgo,
* puede degradarse,
* puede operar aislado temporalmente.

No existe servidor maestro permanente.

---

## 2.5 Persistencia local obligatoria

Cada nodo conserva:

* datasets,
* snapshots,
* estado cluster,
* leases,
* logs,
* histórico.

La caída de un nodo no debe destruir el estado global.

---

# 3. ROLES

## ACTIVE

Nodo que:

* sirve tráfico,
* acepta escrituras,
* coordina replicación,
* publica estado oficial.

Restricción:

```text
solo uno
```

---

## STANDBY

Nodo preparado para takeover.

Debe:

* replicar datasets,
* vigilar activo,
* mantener watchdog,
* permanecer sincronizado.

---

## OBSERVER

Nodo visible pero sin participación activa.

Puede:

* monitorizar,
* consultar,
* desarrollar,
* depurar.

No participa en election.

---

## OFFLINE

Nodo no alcanzable o inválido.

---

# 4. MODELO DE ELECCIÓN

## Regla principal

El nodo activo será:

```text
el nodo sano con menor priority
```

Ejemplo:

```text
priority 1 -> preferido
priority 2 -> backup
priority 3 -> último recurso
```

---

## Requisitos para liderazgo

Un nodo solo puede declararse activo si:

* su watchdog es válido,
* puede acceder a datasets,
* no detecta líder superior sano,
* lease del líder previo expiró,
* cluster state es consistente.

---

# 5. SPLIT BRAIN

El sistema debe minimizar:

```text
múltiples nodos activos simultáneos
```

---

## Política inicial

Ante duda:

```text
preferir degradación antes que doble activo
```

---

## Reglas

Si un nodo detecta:

* líder superior sano,
* lease válido remoto,
* conflicto de autoridad,

debe:

```text
pasar inmediatamente a standby
```

---

# 6. DATASETS

El cluster maneja datasets replicables.

Ejemplos:

* users
* points
* hosts
* sessions
* chat
* telemetry

---

## Propiedades

Cada dataset tendrá:

```text
dataset_id
version
updated_at
source_node
lease_owner
revision
checksum
items
```

---

## Escritura

Solo el nodo activo puede aceptar escrituras.

---

## Réplicas

Los standby:

* descargan snapshots,
* validan checksums,
* mantienen copia local caliente.

---

# 7. REPLICACIÓN

## Modelo inicial

Pull periódico.

Los standby consultan al activo:

```text
/api/datasets/*
```

---

## Frecuencia

Configurable.

Valor inicial recomendado:

```text
5 segundos
```

---

## Consistencia

Modelo:

```text
eventual consistency
```

No se requiere consistencia transaccional distribuida.

---

# 8. WATCHDOG

Cada nodo ejecuta watchdog interno.

Responsabilidades:

* comprobar peers,
* medir latencia,
* validar health,
* detectar stale nodes,
* actualizar cluster state.

---

## Intervalo inicial

```text
10 segundos
```

---

# 9. LEASES

El nodo activo posee un lease temporal.

Ejemplo:

```text
lease_duration_ms = 15000
```

---

## Renovación

El activo debe renovar lease periódicamente.

---

## Expiración

Si lease expira:

* el nodo pierde autoridad,
* standby puede iniciar takeover.

---

# 10. API MÍNIMA

## `/api/health`

Estado básico del nodo.

---

## `/api/cluster`

Estado global del cluster.

---

## `/api/active-node`

Nodo actualmente activo.

---

## `/api/lease`

Información de lease actual.

---

## `/api/datasets/<dataset>`

Acceso a datasets replicables.

---

# 11. PERSISTENCIA

Cada nodo mantiene:

```text
/data
/history
/snapshots
/logs
/state
```

---

# 12. FILOSOFÍA OPERATIVA

El cluster debe:

* funcionar en LAN doméstica,
* tolerar apagados arbitrarios,
* soportar nodos intermitentes,
* reintegrar nodos automáticamente,
* evitar dependencias cloud,
* minimizar complejidad externa.

---

# 13. TECNOLOGÍA BASE

Primera implementación:

* Python
* Flask
* threading
* JSON snapshots
* HTTP polling

---

## Exclusiones iniciales

No usar inicialmente:

* Kubernetes
* Docker Swarm
* etcd
* Redis cluster
* RabbitMQ
* PostgreSQL HA

---

# 14. COMPATIBILIDAD FRV

El sistema debe ser compatible con:

* genealogía documental,
* snapshots FRV,
* versionado estructural,
* trazabilidad de datasets,
* contratos parseables.

---

# 15. OBJETIVO DE FASE 1

Primera milestone:

```text
3 nodos
1 activo
failover automático
replicación datasets
sin split brain
```

---

# 16. REGLA DE DESARROLLO

Antes de implementar nuevas features:

1. definir contrato,
2. definir invariantes,
3. definir ownership,
4. definir estados válidos,
5. definir recuperación de fallo.

Implementación después.
