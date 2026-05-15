Aquí tienes el documento encapsulado.

# DISTRIBUTED DATA STORAGE MODELS

# Objetivo

Resumen conceptual de los principales modelos de almacenamiento usados en sistemas distribuidos modernos.

La idea NO es copiar exactamente Kafka, Raft o bases de datos existentes.

La idea es entender:

* cómo fluye la información
* cómo se persiste
* cómo se replica
* cómo se recupera
* cómo se mantiene consistencia

---

# 1. APPEND ONLY LOG

## Idea principal

Nunca modificar datos.

Sólo añadir eventos nuevos.

```text
event 1
event 2
event 3
event 4
```

---

# Ventajas

* extremadamente robusto
* recovery sencillo
* replicación sencilla
* orden global
* auditoría completa
* replay posible

---

# Uso real

* Kafka
* Raft
* Redis AOF
* Event sourcing
* WAL databases

---

# Estructura típica

```text
wal/
  wal-000001.log
  wal-000002.log
```

Cada línea:

```json
{"seq":1,"event":"message"}
{"seq":2,"event":"gps"}
```

---

# 2. RAFT LOG

## Objetivo

Mantener consenso distribuido.

---

# Idea

Un líder controla:

* orden global
* commits
* replicación

Followers:

* copian exactamente el log
* nunca generan orden propio

---

# Flujo

```text
cliente
   |
   v
leader
   |
   +--> append local log
   +--> replicate followers
   +--> quorum ACK
   +--> COMMIT
```

---

# Características

## fuerte consistencia

Todos los nodos terminan con:

```text
mismo orden
mismos eventos
mismo estado
```

---

# Uso real

* etcd
* Consul
* Kubernetes control plane
* Hashicorp systems

---

# Ventajas

* alta seguridad de datos
* failover limpio
* consenso real

---

# Inconvenientes

* más lento
* quorum obligatorio
* complejidad alta

---

# 3. KAFKA STYLE LOG

## Objetivo

Streaming masivo.

---

# Idea

Los eventos viven permanentemente en topics.

```text
topic: chat
topic: gps
topic: notifications
```

Cada topic:

```text
partition 0
partition 1
partition 2
```

---

# Características

* append-only
* enorme throughput
* replay histórico
* consumers independientes
* persistencia prolongada

---

# Flujo

```text
producer
   |
   v
broker
   |
   +--> append log
```

Consumers leen después.

---

# Ventajas

* escalabilidad brutal
* desacoplamiento total
* ideal para eventos

---

# Inconvenientes

* consistencia más compleja
* ordering parcial
* más difícil para writes críticos

---

# 4. EVENT SOURCING

## Idea

Guardar EVENTOS.

NO estado final.

---

# Ejemplo

NO guardar:

```json
{
  "balance": 150
}
```

Guardar:

```json
{"event":"deposit","amount":100}
{"event":"deposit","amount":50}
```

Estado final:

```text
100 + 50 = 150
```

---

# Ventajas

* replay
* auditoría
* debugging
* time-travel
* reconstrucción

---

# Inconvenientes

* reconstrucción costosa
* snapshots necesarios

---

# 5. SNAPSHOTS

## Problema

No puedes replay infinito.

---

# Solución

Cada cierto tiempo:

```text
snapshot-000001.dat
```

Ejemplo:

```json
{
  "last_seq": 500000,
  "users_online": [...]
}
```

---

# Recovery

```text
snapshot + WAL restante
```

---

# 6. SHARDING

## Idea

Dividir datos entre nodos.

---

# Ejemplo

```text
server A -> users 1..1M
server B -> users 1M..2M
```

---

# Ventajas

* escalabilidad horizontal

---

# Inconvenientes

* routing complejo
* rebalanceo complejo
* consistencia difícil

---

# 7. FULL REPLICATION

## Idea

Todos los nodos tienen copia completa.

---

# Ventajas

* failover simple
* recovery simple
* lecturas distribuidas

---

# Inconvenientes

* mucho almacenamiento
* más tráfico red

---

# Recomendación para MAYHEM CLUSTER

## FASE 1

Usar:

```text
RAFT-LIKE REPLICATED WAL
```

---

# Modelo recomendado

## leader

* recibe writes
* asigna sequence
* append WAL
* replica followers

---

## followers

* replican WAL
* validan ordering
* standby listos

---

# Estructura recomendada

```text
cluster_data/

  wal/
    2026-05-14/
      wal-000001.log

  snapshots/
      snapshot-000001.json
```

---

# Formato recomendado

JSONL.

```json
{"seq":1822,"ts":1778785000,"type":"chat","payload":{...}}
```

---

# Objetivo conceptual final

NO pensar:

```text
base de datos clásica
```

Pensar:

```text
stream distribuido de eventos ordenados
```

Ese es el núcleo conceptual de sistemas distribuidos modernos.
