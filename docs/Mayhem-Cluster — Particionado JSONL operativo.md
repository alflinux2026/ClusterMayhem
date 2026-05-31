# Mayhem-Cluster — Particionado JSONL operativo

## Objetivo

Definir el contrato final de particionado del flujo de eventos de Mayhem-Cluster para cerrar el core, congelar la lógica de infraestructura y dejar el consumo de datos a workers y aplicaciones superiores.

El cluster actúa como receptor neutral de eventos, persistencia canónica y fuente de verdad histórica. El particionado JSONL separa el histórico bruto del histórico operativo y de los datos listos para proyección.

## Alcance

Este documento cubre:

- Entrada de eventos.
- Particiones internas de JSONL.
- Criterios de corte entre estados.
- Consumo por el worker de distribución.
- Tratamiento de eventos desconocidos.

No cubre la lógica de la aplicación superior ni la implementación concreta del worker.

## Principios

- El log canónico es la verdad primaria.
- El cluster no interpreta negocio.
- El worker proyecta, no inventa.
- Los JSONL derivados son vistas materializadas, no copias semánticas.
- Todo evento debe ser reprocesable desde el histórico.

## Entradas

El particionado se alimenta de `ClusterEvent` con esta información mínima:

- `event_id`
- `event_type`
- `schema_version`
- `trace_id`
- `source_node`
- `target_node`
- `status`
- `attempt`
- `execution_key`
- `payload`

Además, cada evento debe conservar metadatos técnicos de tiempo y origen para trazabilidad y reconstrucción.

## Particiones

Se definen cuatro zonas lógicas:

### 1. `event_log.local.jsonl`
Log canónico completo. Contiene todos los eventos aceptados por el cluster en orden append-only.

### 2. `event_log.accepted.jsonl`
Subconjunto de eventos admitidos por el cluster para procesamiento posterior.

### 3. `event_log.completed.jsonl`
Subconjunto de eventos cerrados técnicamente y listos para consumo del worker de distribución.

### 4. JSONL derivados por dominio
Archivos de salida materializados por familia de eventos, por ejemplo:

- `gps_points.jsonl`
- `chat_messages.jsonl`
- `telemetry_samples.jsonl`
- `device_status.jsonl`
- `commands_executed.jsonl`

## Criterios de corte

### Aceptación
Un evento pasa a la partición `accepted` cuando:

- Ha sido recibido por el cluster.
- Ha sido validado mínimamente a nivel técnico.
- Ha sido persistido en el log canónico.

### Compleción técnica
Un evento pasa a `completed` cuando:

- Está persistido.
- Está replicado o confirmado según el flujo interno del cluster.
- Su estado técnico indica que puede ser consumido por el worker.

### Proyectabilidad
Un evento se considera proyectable cuando:

- Su `event_type` pertenece a una familia reconocida.
- Su `payload` puede normalizarse sin pérdida crítica.
- No requiere lógica de negocio del cluster para ser interpretado.

## Regla por `event_type`

### `map.*`
- Se acepta.
- Se marca como proyectable.
- Se envía a proyección geoespacial.
- Ejemplo de salida: `gps_points.jsonl`.

### `chat.*`
- Se acepta.
- Se marca como proyectable.
- Se envía a proyección conversacional.
- Ejemplo de salida: `chat_messages.jsonl`.

### `telemetry.*`
- Se acepta.
- Se marca como proyectable.
- Se envía a proyección temporal.
- Ejemplo de salida: `telemetry_samples.jsonl`.

### `cmd.*`
- Se acepta.
- Se marca como ejecutable.
- Puede ir a dispatch operativo.
- Si genera derivado, será de auditoría, no de consumo primario.

### `job.*`
- Se acepta.
- Se marca como ejecutable.
- Puede ir a dispatch operativo.
- Si genera derivado, será de auditoría, no de consumo primario.

### Desconocidos
- Se aceptan.
- Se conservan en el log canónico.
- No se proyectan automáticamente.
- Pueden ir a una partición de cuarentena o auditoría.

## Consumo por el worker

El worker de distribución consume exclusivamente desde `event_log.completed.jsonl` o equivalente operativo estable.

Su secuencia es:

1. Leer evento confirmado.
2. Clasificar por `event_type`.
3. Normalizar `payload`.
4. Escribir una línea en el JSONL derivado correspondiente.
5. Registrar trazabilidad de proyección.
6. Dejar intacto el log canónico.

Si el evento no pertenece a una familia conocida, el worker no falla el proceso general; simplemente omite la proyección o lo envía a una partición de auditoría.

## Tratamiento de eventos desconocidos

Los eventos desconocidos se conservan siempre.

Comportamiento:

- No se interpreta semántica no declarada.
- No se ejecuta lógica automática sobre ellos.
- No bloquean el ingest ni el cierre del evento.
- Se guardan para inspección, evolución futura o reprocesado manual.

## Contrato operativo final

- El cluster ingiere.
- El cluster conserva.
- El cluster replica.
- El cluster particiona.
- El worker proyecta.
- La aplicación superior consume.

## Cierre

Con este particionado, Mayhem-Cluster queda listo para congelarse como core estable. A partir de aquí, el trabajo pasa a los workers de distribución y a la aplicación superior, sin seguir contaminando el centro con lógica de dominio.

## Estado

Versión inicial operativa.
Listo para integración y cierre del core.





## Cierre del diseño

Con este documento queda fijada la arquitectura final de Mayhem-Cluster como core neutral de entrada y persistencia de datos para el ecosistema Mayhem. El cluster no interpreta semántica de aplicación, no acopla el dominio de negocio y no incorpora lógica específica de la app superior; su función termina en la ingesta, el registro canónico, la replicación y el particionado operativo.[file:1][file:2]

El campo `event_type` se considera únicamente una clave de enrutado para el worker de distribución. La interpretación real del dato, la generación de vistas JSONL derivadas y el consumo de esas vistas quedan fuera del cluster y pasan a pertenecer a capas superiores del sistema.[file:2]

A partir de aquí, el comportamiento esperado es estable y congelable: el cluster acepta eventos heterogéneos, los conserva en el log canónico, los marca para su estado técnico correspondiente y expone la base necesaria para que el worker proyecte por familias de `event_type` sin modificar el corazón del sistema.[file:1][file:2]

## Decisión final

- Mayhem-Cluster queda cerrado como infraestructura neutral.
- `event_type` solo sirve para distribución y proyección.
- El worker de distribución opera por prefijos o patrones de `event_type`.
- Las aplicaciones superiores consumen JSONL derivados, no el log bruto.
- El core no vuelve a ampliarse con lógica de dominio salvo correcciones técnicas inevitables.[file:1][file:2]

## Estado operativo

Con este cierre, Mayhem-Cluster pasa a fase estable de mantenimiento mínimo. El siguiente trabajo ya no es “hacer más cluster”, sino ejecutar el worker, consolidar las particiones JSONL y conectar la aplicación superior sobre esa base desacoplada.[file:1][file:2]

## Resultado

Mayhem-Cluster queda definido como base común del ecosistema Mayhem, listo para servir datos desde una infraestructura limpia, independiente y reproducible. A partir de aquí, el sistema superior manda y el cluster obedece; justo como debe ser cuando dejas de improvisar y empiezas a construir en serio.[file:1][file:2]
