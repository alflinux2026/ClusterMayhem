# Mayhem-Cluster — Status EOD y boot session

## Estado general

Mayhem-Cluster ya está en una fase útil de consolidación como base de entrada de datos para el ecosistema Mayhem. El core actual soporta un sobre genérico `ClusterEvent`, ingesta vía `/event`, persistencia append-only en JSONL y replicación entre nodos, por lo que la arquitectura base está bastante encaminada.[file:596]

La dirección correcta ya está clara: el cluster no debe “entender” el dominio de negocio de cada aplicación, sino actuar como receptor, registro y proyector de datos. Eso permite que aplicaciones futuras consuman datos ya materializados sin acoplarse al log crudo ni al runtime del cluster.[file:596][web:946]

## Hecho hoy

- Se ha cerrado la idea de usar Mayhem-Cluster como puerta de entrada común de datos para todo el ecosistema.
- Se ha validado que el payload del evento puede ser genérico y servir para GPS, chat, telemetría o cualquier otra fuente.
- Se ha decidido que la ejecución puede reutilizarse como capa de proyección a JSONL derivados.
- Se ha documentado la arquitectura objetivo en Markdown para poder iterar y afinar el diseño.[file:596][web:946]

## Decisiones ya tomadas

- El cluster debe ser neutral respecto al tipo de dato.
- `event_type` será la clave semántica principal para clasificar flujos.
- El log canónico sigue siendo la fuente de verdad.
- Las proyecciones derivadas serán insumos de las apps superiores.
- Los eventos tipo `map.*`, `chat.*` y `telemetry.*` tenderán a ingesta + proyección, mientras que `cmd.*` y `job.*` podrán seguir el camino de ejecución.[file:596][web:953]

## Estado técnico actual

El core ya tiene la base necesaria para no tocar demasiado la capa de transporte. `ClusterEvent` incluye `event_type` y `payload` como campos flexibles, y el endpoint `/event` ya reenvía al líder y persiste el evento en el log local.[file:596]

También existe la posibilidad de usar la fase de ejecución para producir archivos JSONL derivados, lo que encaja con un patrón de proyección o vista materializada. Eso simplifica el consumo posterior y mantiene el log bruto intacto para reprocesado o reconstrucción.[web:955][web:946]

## Pendiente inmediato

- Probar una PoC web móvil que capture GPS real.
- Enviar eventos `map.gps` al cluster.
- Verificar persistencia y replicación.
- Implementar la primera proyección `gps_points.jsonl`.
- Confirmar que una app superior puede consumir esa proyección sin tocar el log bruto.[file:596][web:943]

## Riesgos abiertos

El principal riesgo es mezclar demasiado pronto la semántica de negocio con el core del cluster. Si todo termina entrando en el mismo flujo de ejecución sin filtrado por tipo, el sistema deja de ser una puerta de entrada genérica y se convierte otra vez en un runtime con lógica acoplada.[file:596]

Otro riesgo es proliferar demasiados JSONL derivados sin convención clara. La solución es mantener pocas proyecciones estables, versionadas y reconstruibles desde el log canónico.[web:951][web:946]

## Boot session posterior

### Objetivo de la próxima sesión

Retomar con el cluster ya documentado y avanzar hacia una primera implementación de proyección orientada a datos reales. El foco no debe ser “hacer más lógica”, sino **reducir acoplamiento** y cerrar el circuito ingestión → persistencia → proyección → consumo.[file:596][web:946]

### Orden recomendado

1. Revisar el contrato final de `ClusterEvent` para asegurar que sigue sirviendo como sobre universal.
2. Definir qué `event_type` se consideran solo datos y cuáles se ejecutan.
3. Añadir la primera proyección JSONL, empezando por GPS.
4. Preparar la web móvil simple para enviar eventos reales.
5. Verificar lectura desde una app superior o desde una herramienta de inspección.[file:596][web:943][web:955]

## Cierre operativo

El estado a día de hoy es bueno: no hace falta rehacer el cluster, hace falta terminar de convertirlo en infraestructura de entrada y publicación de datos. Si la próxima iteración confirma la captura móvil y la proyección a JSONL, Mayhem-Cluster quedará listo para empezar a servir de base común a futuras aplicaciones del ecosistema Mayhem.[file:596][web:946]
