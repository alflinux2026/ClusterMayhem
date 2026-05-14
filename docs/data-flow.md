````md id="distributed-data-flow-design"
# DISTRIBUTED DATA FLOW — DISEÑO BASE

## Objetivo

Definir un modelo estándar de manejo de datos para aplicaciones distribuidas sobre el cluster:

- chat tipo WhatsApp
- tracking tipo Life360
- eventos futuros
- telemetría
- logs
- notificaciones
- cualquier aplicación basada en eventos

El objetivo es separar completamente:

- infraestructura de cluster
- lógica de datos
- lógica de aplicación

---

# PRINCIPIO FUNDAMENTAL

## El cluster NO comparte estado directamente

El cluster:

- NO sincroniza objetos
- NO sincroniza memoria
- NO comparte variables

El cluster SOLO replica:

# EVENTOS

---

# MODELO UNIVERSAL

Todo dato de cualquier aplicación se representa como un evento.

Ejemplo genérico:

```json
{
  "app": "chat",
  "type": "message",
  "source": "userA",
  "timestamp": 123456789,
  "payload": {}
}
````

---

# EJEMPLOS

## Chat

```json
{
  "app": "chat",
  "type": "message",
  "source": "userA",
  "payload": {
    "to": "userB",
    "text": "hola"
  }
}
```

---

## GPS / Life360

```json
{
  "app": "location",
  "type": "position",
  "source": "device_1",
  "payload": {
    "lat": 37.17,
    "lng": -3.60,
    "accuracy": 5
  }
}
```

---

# ARQUITECTURA BASE

## Roles

### Leader

* único nodo que acepta escrituras
* asigna orden global
* replica eventos

### Followers / Backups

* reciben replicación
* almacenan copia
* pueden asumir liderazgo si el líder cae

---

# COMPONENTES DEL SISTEMA

Cada nodo mantiene:

```python
event_log = []
last_seq_applied = 0
current_leader = "node_id"
```

---

# FLUJO COMPLETO DE DATOS

## Escenario

Dos servidores:

* S1 → líder
* S2 → backup

Cliente envía un evento.

---

# PASO 1 — Cliente envía evento

```http
POST /event
```

Destino:

* S1 (líder)

---

# PASO 2 — Leader recibe evento

El líder:

## valida liderazgo

```python
if not is_leader():
    reject()
```

---

## asigna secuencia global

```python
seq = global_counter + 1
```

Ejemplo:

```python
seq = 104
```

---

## crea entrada final

```json
{
  "seq": 104,
  "app": "chat",
  "type": "message",
  "source": "userA",
  "timestamp": 123456,
  "payload": {
    "text": "hola"
  }
}
```

---

## append local

```python
event_log.append(event)
```

---

# PASO 3 — Replicación

Leader envía:

```http
POST /replicate
```

a followers.

Payload:

```json
{
  "seq": 104,
  "event": {...}
}
```

---

# PASO 4 — Follower recibe réplica

Follower:

## valida orden

```python
if seq == last_seq_applied + 1:
```

---

## aplica evento

```python
event_log.append(event)
last_seq_applied = seq
```

---

# PASO 5 — ACK

Follower responde:

```json
{
  "ok": true
}
```

---

# PASO 6 — Confirmación final

Leader:

* espera ACK
* responde al cliente

```http
200 OK
```

---

# RESULTADO FINAL

Todos los nodos contienen:

```text
[102]
[103]
[104]
```

Mismo orden.
Misma historia.
Mismo estado reconstruible.

---

# PRINCIPIO IMPORTANTE

El sistema NO replica estado.

Replica:

# HISTORIAL DE EVENTOS

---

# RECONSTRUCCIÓN DE ESTADO

El estado actual siempre puede recalcularse desde eventos.

Ejemplo:

## Chat

* lista de mensajes
* usuarios conectados

## GPS

* última posición conocida
* historial de movimiento

---

# VENTAJAS

## Consistencia

Todos los nodos comparten mismo orden.

## Replay

El sistema puede reconstruirse desde cero.

## Tolerancia a fallos

Si cae el líder:

* follower puede asumir control
* datos siguen existiendo

## Generalización

Mismo sistema sirve para:

* chat
* GPS
* telemetría
* notificaciones
* logs
* IoT
* eventos de negocio

---

# PROBLEMAS ACTUALES DEL CLUSTER

Actualmente el cluster:

* no tiene log distribuido
* no replica eventos
* no tiene orden global real
* solo sincroniza vistas temporales

---

# EVOLUCIÓN NATURAL DEL PROYECTO

## Fase 1

Leader único writer.

## Fase 2

Replicación de eventos.

## Fase 3

Confirmación de réplica (ACK).

## Fase 4

Recuperación de logs tras fallo.

## Fase 5

Quorum y consenso real.

---

# CONCLUSIÓN

La arquitectura correcta NO consiste en:

* compartir memoria
* sincronizar variables
* replicar estado mutable

La arquitectura correcta consiste en:

# replicar eventos ordenados

y reconstruir el estado desde dichos eventos.

```
```
