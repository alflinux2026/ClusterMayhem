# Mayhem-Cluster como puerta de entrada de datos del ecosistema Mayhem

## Objetivo

Mayhem-Cluster puede evolucionar de runtime orientado a eventos ejecutables a una **puerta de entrada de datos** común para todas las aplicaciones futuras del ecosistema Mayhem. El core actual ya dispone de un sobre genérico (`ClusterEvent`), un endpoint de entrada (`/event`), persistencia append-only en JSONL y replicación entre nodos, lo que permite recibir datos heterogéneos sin rediseñar el transporte base.[cite:1]

La idea objetivo es que el cluster reciba datos de múltiples orígenes y dominios —por ejemplo GPS, chat, telemetría, estado de dispositivos o eventos funcionales— y los conserve de forma consistente para que capas superiores los consuman más tarde. En ese modelo, el cluster actúa como bus de ingestión, bitácora de verdad y sistema de replicación; la lógica de interpretación queda desplazada a proyecciones y aplicaciones consumidoras.[cite:1][cite:2]

## Estado actual del core

El estado actual del core ya encaja bastante bien con una arquitectura de ingesta genérica. `ClusterEvent` define un `event_type` y un `payload` flexible de tipo `dict`, lo que permite transportar datos arbitrarios dentro de una misma envoltura técnica.[cite:1]

El endpoint `/event` acepta ese sobre, reenvía al líder cuando el nodo receptor no lo es y finalmente llama a `ingest_event`, que marca el evento como `CREATED` y lo persiste en el log local. Ese flujo demuestra que el cluster ya sabe recibir, sellar temporalmente y almacenar eventos sin depender del dominio del payload.[cite:1]

La persistencia actual en `append_event()` también es suficientemente genérica para una primera fase. El registro serializa `event_id`, `event_type`, `schema_version`, `trace_id`, `source_node`, `target_node`, `status`, `attempt`, `execution_key` y `payload`, lo que convierte al JSONL local en una fuente de verdad razonable para reconstrucción posterior, auditoría o reproyección.[cite:1][cite:3]

## Lo que ya funciona sin tocar el cluster

Para una prueba rápida con web móvil, no hace falta rehacer el cluster. Se puede enviar un `ClusterEvent` con `event_type="map.gps"` y un `payload` con latitud, longitud, precisión, timestamp y metadatos del dispositivo, y el cluster lo aceptará, lo reenviará al líder si procede, lo persistirá y lo replicará como cualquier otro evento.[cite:1]

Este enfoque encaja especialmente bien con una PoC basada en navegador móvil. La Geolocation API del navegador permite obtener ubicación real del dispositivo, con permiso del usuario, y enviarla por `fetch()` en formato JSON al backend; para que eso funcione en navegadores modernos suele requerirse contexto seguro, normalmente HTTPS.[cite:4][cite:5]

La consecuencia práctica es clara: para validar el concepto de “cluster como puerta de entrada común”, basta con construir un cliente ligero que produzca eventos `map.gps` usando el contrato actual. Esa prueba permite comprobar ingesta, almacenamiento, forwarding al líder y trazabilidad sin introducir todavía una capa específica por dominio.[cite:1][cite:5]

## Limitación arquitectónica actual

Aunque el cluster ya puede recibir tipos de datos diversos, todavía no está completamente desacoplado de la idea de “evento ejecutable”. Tras la ingesta, el flujo normal entra en `dispatch_tick()`, selecciona un target worker y termina en `execute_event()`, donde el evento se marca como `COMPLETED` después de ejecutar una lógica de negocio genérica.[cite:1]

Ese diseño funciona bien para comandos o trabajos distribuidos, pero no es ideal para datos crudos que solo deben ser recibidos y almacenados. Si todos los tipos de eventos se tratan como trabajos ejecutables, el cluster deja de ser un receptor neutral y pasa a asumir semánticas que deberían pertenecer a capas superiores.[cite:1][cite:2]

Por tanto, la evolución deseable no es sustituir el core, sino introducir una separación más explícita entre **ingesta** y **ejecución**. Esa separación permitiría que algunos eventos sean solamente conservados y replicados, mientras que otros activen procesos derivados controlados.[cite:1][cite:2]

## Principio rector de diseño

La decisión de diseño más importante es esta: al cluster debe darle igual el significado funcional del dato. Su responsabilidad debe limitarse a aceptar eventos, enriquecerlos con metadatos técnicos, persistirlos, replicarlos y exponerlos para consumo posterior.[cite:1][cite:2]

La interpretación de `map.gps`, `chat.message`, `telemetry.temperature` o `job.command` no debería residir en el corazón del transporte. Esa semántica debe vivir en proyecciones, consumidores, pipelines o servicios del ecosistema que trabajen **encima** del cluster, no dentro del bus de entrada.[cite:2][cite:6]

Este enfoque se alinea con patrones de event sourcing y vistas materializadas: el log append-only actúa como fuente de verdad, mientras que otras piezas construyen representaciones derivadas optimizadas para consulta o explotación. La ventaja es que cualquier vista rota o rediseñada puede reconstruirse reprocesando el log canónico.[cite:6][cite:8][cite:10]

## Propuesta de arquitectura objetivo

La arquitectura objetivo puede expresarse en cuatro capas:

- **Captura**: clientes web, apps móviles, dispositivos, integraciones externas.
- **Ingesta cluster**: recepción, validación mínima, metadatos, persistencia, replicación.
- **Proyección**: materialización de JSONL derivados por dominio o por caso de uso.
- **Consumo**: aplicaciones Mayhem que leen proyecciones o rehidratan historia desde el log base.[cite:1][cite:6]

En esta arquitectura, `ClusterEvent` sigue siendo la envoltura universal y el `payload` continúa siendo genérico. La semántica la aporta `event_type`, que debe convertirse en la clave principal para enrutar proyecciones, reglas de retención y consumidores posteriores.[cite:1]

Una convención inicial útil sería esta:

| Categoría | Ejemplo | Tratamiento sugerido |
|---|---|---|
| `map.*` | `map.gps` | Ingesta + proyección geoespacial [cite:1] |
| `chat.*` | `chat.message` | Ingesta + proyección de mensajes [cite:1] |
| `telemetry.*` | `telemetry.temperature` | Ingesta + proyección de series temporales [cite:1] |
| `cmd.*` | `cmd.run_task` | Ingesta + dispatch + ejecución [cite:1] |
| `job.*` | `job.reconcile` | Ingesta + dispatch + ejecución [cite:1] |

Esta convención no exige rehacer el modelo, solo usar mejor el campo `event_type`. El core ya lo persiste y lo replica, así que la clasificación por familia puede introducirse de manera incremental.[cite:1]

## Uso de la ejecución como proyección

La conversación técnica ha llevado a una idea especialmente valiosa: reutilizar la fase de `execute_event()` no para negocio complejo, sino para **materializar archivos JSONL derivados** que sirvan de insumo a las aplicaciones superiores. Ese patrón es coherente con el uso de proyecciones y vistas materializadas derivadas de un log canónico.[cite:6][cite:8]

En ese modelo, el flujo sería:

1. El cluster ingiere el evento bruto y lo guarda en `event_log.local.jsonl`.
2. Una fase de ejecución/proyección lee el evento aceptado.
3. Según `event_type`, escribe una representación derivada en un JSONL específico.
4. La aplicación de arriba consume ese JSONL derivado, no el log bruto completo.[cite:1][cite:6]

Por ejemplo, un evento `map.gps` podría terminar en un archivo `gps_points.jsonl`; un `chat.message` en `chat_messages.jsonl`; y un `device.status` en `device_status.jsonl`. Esto reduce acoplamiento, simplifica los consumidores y mantiene el log base como verdad histórica independiente de la forma de explotación.[cite:6][cite:9]

## Tipos de archivos derivados recomendados

No conviene generar un archivo derivado por cada capricho puntual. Una estrategia más robusta es mantener un conjunto pequeño y estable de proyecciones por dominio o por caso de uso principal.[cite:9]

Una primera propuesta razonable para el ecosistema Mayhem sería:

| Archivo derivado | Fuente principal | Uso posterior |
|---|---|---|
| `gps_points.jsonl` | `map.gps` | mapas, replay de trayectorias, tracking [cite:1] |
| `chat_messages.jsonl` | `chat.message` | timeline, búsqueda, UI de conversación [cite:1] |
| `telemetry_samples.jsonl` | `telemetry.*` | gráficas, alertas, análisis de series [cite:1] |
| `device_status.jsonl` | `device.status` | estado actual por dispositivo, dashboards [cite:1] |
| `commands_executed.jsonl` | `cmd.*`, `job.*` | auditoría operativa y trazabilidad [cite:1] |

Estos archivos pueden actuar como insumos directos para aplicaciones futuras sin obligarlas a parsear el log canónico completo. Si más adelante cambian sus necesidades, siempre se podrán regenerar desde la historia original almacenada por el cluster.[cite:6][cite:8]

## Prueba rápida con web móvil y GPS real

La primera validación recomendada es una PoC de web móvil rápida. Una página servida por un frontend ligero puede usar `navigator.geolocation.watchPosition()` para obtener coordenadas reales del móvil y enviar cada muestra al endpoint `/event` del cluster en formato `ClusterEvent`.[cite:4][cite:5]

El payload mínimo debería incluir `device_id`, `ts`, `lat`, `lon`, `accuracy_m`, y opcionalmente `speed_mps`, `heading_deg` y metadatos de origen. Esa estructura es suficiente para empezar a almacenar puntos, proyectarlos a `gps_points.jsonl` y verificar que el cluster funciona como puerta de entrada de datos del ecosistema.[cite:1][cite:5]

Un ejemplo sintético del payload sería este:

```json
{
  "event_type": "map.gps",
  "payload": {
    "kind": "gps",
    "device_id": "mobile-web-01",
    "ts": 1716590700.123,
    "lat": 39.4699,
    "lon": -0.3763,
    "accuracy_m": 8.5,
    "speed_mps": 0,
    "heading_deg": 0,
    "source": "mobile_browser"
  }
}
```

Con ese formato ya se puede ensayar captura real, transporte, persistencia y proyección sin introducir todavía complejidad innecesaria. Como PoC arquitectónica, es una prueba excelente porque fuerza al cluster a comportarse como receptor neutral de datos externos.[cite:1][cite:5]

## Cambios mínimos recomendados en el core

El cambio más importante no es ampliar el modelo de datos, porque eso ya está bastante resuelto. El cambio importante es **decidir qué tipos de eventos disparan ejecución/proyección y cuáles solo se almacenan**.[cite:1]

Una política inicial simple podría ser:

- `map.*`, `chat.*`, `telemetry.*` → ingesta + proyección a JSONL derivado.
- `cmd.*`, `job.*` → ingesta + dispatch + ejecución operativa.
- cualquier otro tipo desconocido → ingesta y almacenamiento, sin ejecución automática.[cite:1]

Esto convierte al cluster en algo mucho más cercano a una puerta de entrada universal. Además, evita el error de tratar datos pasivos como trabajos distribuidos, que es el principal punto en el que hoy la arquitectura todavía está demasiado orientada a runtime de comandos.[cite:1][cite:2]

## Principios operativos para cerrar Mayhem-Cluster

Para cerrar Mayhem-Cluster como plataforma transversal del ecosistema, conviene fijar una serie de principios operativos:

- El log append-only es la verdad histórica primaria.[cite:6][cite:10]
- `ClusterEvent` es el sobre universal para todo dato que entra.[cite:1]
- `event_type` define semántica, ruta de proyección y posibles consumidores.[cite:1]
- El core no interpreta negocio; solo enruta, persiste, replica y proyecta lo mínimo necesario.[cite:1][cite:2]
- Las apps de nivel superior leen proyecciones o reconstruyen historia desde el log canónico.[cite:6][cite:8]
- Las proyecciones deben ser reconstruibles desde cero.[cite:6][cite:10]

Si estos principios se respetan, el cluster deja de ser solo un runtime distribuido y pasa a ser una base estructural del ecosistema Mayhem. Eso le permite servir hoy para GPS y mañana para chat, telemetría industrial, eventos de automatización o cualquier otra fuente futura sin rediseño del corazón de transporte.[cite:1][cite:2]

## Decisiones abiertas

Todavía quedan varias decisiones de diseño por cerrar antes de dar la arquitectura por definitiva:

- si `execute_event()` debe seguir existiendo como nombre o renombrarse a algo más neutral, como `project_event()` o `materialize_event()`; [cite:1]
- si las proyecciones se escriben en el mismo nodo líder, en todos los nodos o en un subconjunto; [cite:1]
- si el consumo superior leerá JSONL directamente o a través de endpoints de consulta; [cite:1]
- cómo versionar `event_type` y `payload` cuando aparezcan cambios de contrato entre aplicaciones. [cite:1][cite:9]

Estas decisiones no bloquean la PoC, pero sí conviene documentarlas porque condicionan la escalabilidad y el mantenimiento del ecosistema. La buena noticia es que ninguna obliga a rehacer el corazón del cluster: todas pueden resolverse incrementalmente sobre la base actual.[cite:1]

## Siguiente iteración recomendada

La siguiente iteración práctica y de bajo riesgo sería esta:

1. Probar una web móvil rápida que envíe eventos `map.gps` reales al cluster.[cite:4][cite:5]
2. Confirmar que el leader los persiste y los replica correctamente.[cite:1]
3. Añadir una primera proyección `gps_points.jsonl` desde la fase de ejecución/proyección.[cite:1][cite:6]
4. Verificar que una aplicación superior puede leer ese JSONL como insumo estable.[cite:6][cite:8]
5. Generalizar el patrón a `chat.*` y `telemetry.*` solo después de validar el circuito completo.[cite:1]

Ese camino permite cerrar el diseño con una base real, no solo teórica. También reduce el riesgo de sobrearquitectura temprana, algo especialmente importante en un sistema que pretende servir de base común a múltiples aplicaciones futuras.[cite:6][cite:9]

## Conclusión

Mayhem-Cluster ya dispone de los elementos básicos para actuar como puerta de entrada de datos del ecosistema: sobre genérico, endpoint de entrada, almacenamiento append-only, replicación y trazabilidad técnica. La evolución necesaria no consiste en rehacer el core, sino en consolidar una filosofía de neutralidad del dato y desacoplar claramente la ingesta del procesamiento específico de dominio.[cite:1][cite:2]

Bajo ese enfoque, la ejecución puede reutilizarse como mecanismo de proyección hacia JSONL derivados, y la primera validación natural es una PoC de GPS real desde web móvil. Si esa prueba funciona y las proyecciones quedan claras, Mayhem-Cluster tendrá una base sólida para servir como puerta de entrada compartida de todas las aplicaciones futuras del ecosistema Mayhem.[cite:4][cite:5][cite:6]
