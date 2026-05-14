Aquí tienes el documento encapsulado para guardar/exportar.

# CLIENT → CLUSTER → DATA FLOW

## Objetivo

Diseñar una forma estándar de comunicación entre clientes y cluster para cualquier aplicación futura:

* chat tipo WhatsApp
* tracking tipo Life360
* eventos
* telemetría
* sincronización
* notificaciones
* etc.

La idea es que el cliente NO tenga lógica compleja de cluster.

El cluster absorbe toda la complejidad.

---

# Principio principal

El cliente habla con el CLUSTER.

NO con un líder concreto.

El cluster decide internamente:

* quién es líder
* quién procesa writes
* quién replica
* quién responde

---

# Arquitectura recomendada

```text
CLIENTE
   |
   v
ANY NODE (entrypoint)
   |
   +--> si es líder:
   |        procesa write
   |
   +--> si NO es líder:
            proxy interno al líder
```

El cliente no necesita saber qué nodo es líder.

---

# Descubrimiento inicial del cluster

El cliente puede llevar una lista básica:

```json
[
  "100.100.1.200:7000",
  "100.100.1.202:7000",
  "100.100.1.203:7000"
]
```

El cliente intenta conectar con cualquiera.

Si uno falla:
prueba el siguiente.

---

# Flujo WRITE recomendado

## Caso normal

```text
cliente
   |
   v
backup node
   |
   v
leader
   |
   +--> append WAL
   +--> persist local
   +--> replicate backups
   +--> quorum ACK
   +--> COMMIT
   |
   v
respuesta OK
```

---

# WAL (Write Ahead Log)

Antes de confirmar un dato:

1. líder escribe evento en log
2. líder replica evento
3. backups confirman recepción
4. líder marca commit
5. líder responde OK

Esto evita pérdida de datos.

---

# Replicación

## Modelo recomendado

### leader → followers

Sólo el líder:

* acepta writes reales
* genera secuencia global
* asigna ordering
* replica

Los backups:

* almacenan copia
* validan integridad
* pueden promocionarse a líder

---

# READS

## Opción 1 — strict consistency

Siempre responder desde líder.

Más seguro.

Más lento.

---

## Opción 2 — eventual consistency

Cualquier nodo responde.

Más rápido.

Puede haber unos milisegundos/segundos de retraso.

---

# Recomendación según aplicación

## Chat tipo WhatsApp

### WRITES

Siempre al líder.

### READS

Puede responder cualquier nodo.

---

## GPS / tracking / Life360

Puede tolerar:

```text
eventual consistency
```

Perder un update GPS ocasional no suele ser crítico.

---

# Diseño estándar de eventos

Todos los datos deberían viajar como eventos.

Ejemplo:

```json
{
  "event_id": "uuid",
  "stream": "chat.room.123",
  "timestamp": 1778785000,
  "node": "lnx200nas",
  "sequence": 18422,
  "payload": {
    "user": "alf",
    "message": "hola"
  }
}
```

---

# Principio importante

NO almacenar “estado final”.

Almacenar EVENTOS.

Luego el estado se reconstruye.

Esto permite:

* replay
* auditoría
* recuperación
* sincronización
* replicación
* debugging
* time-travel
* reconstrucción parcial

---

# Componentes futuros necesarios

## 1. WAL

Write Ahead Log.

---

## 2. Replication Queue

Cola de replicación líder → backups.

---

## 3. Commit Index

Último evento confirmado globalmente.

---

## 4. Sequence Generator

Secuencia monotónica global.

---

## 5. Snapshot System

Snapshots periódicos para evitar replay infinito.

---

# Estado actual del cluster

Actualmente el cluster YA tiene:

* heartbeat
* propagación de estado
* cluster membership
* cleanup TTL
* detección de caída
* elección automática de líder
* recuperación automática de líder

Falta construir:

```text
DATA PLANE
```

es decir:

* persistencia real
* replicación real
* commit real
* consenso real
* WAL real

---

# Próxima prueba recomendada

## datatest

Objetivo:

Sólo el líder genera datos.

Cada X segundos:

```json
{
  "timestamp": "...",
  "leader": "lnx200nas",
  "counter": 1822
}
```

Luego:

* matar líder
* recuperar líder
* verificar gaps
* medir pérdida
* verificar ordering
* medir convergencia

Esta prueba ya valida el comienzo del data plane distribuido.
