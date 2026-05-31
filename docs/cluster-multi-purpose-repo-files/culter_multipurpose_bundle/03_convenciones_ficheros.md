# Culter Multi Purpose — Convenciones de ficheros

## Estructura base
```text
data/<tenant_id>/<app_id>/<data_type>/<schema_version>/current.jsonl
data/<tenant_id>/<app_id>/<data_type>/<schema_version>/segments/000001.jsonl
data/<tenant_id>/<app_id>/<data_type>/<schema_version>/segments/000001.meta.json
data/<tenant_id>/<app_id>/<data_type>/<schema_version>/segments/000002.jsonl
```

## Ejemplos
```text
data/tenantA/appFoo/telemetry/v1/current.jsonl
data/tenantA/appFoo/telemetry/v1/segments/000014.jsonl
data/tenantA/appFoo/telemetry/v1/segments/000014.meta.json
```

## Regla de naming
- `tenant_id`: dueño o ámbito lógico.
- `app_id`: frontend o aplicación emisora.
- `data_type`: clase semántica del dato.
- `schema_version`: versión del contrato.
- `segment_id`: unidad física cerrada.

## Objetivo operativo
Separar streams lógicos y permitir que el core aplique las mismas políticas de rotación, réplica e integridad sin mezclar tipos incompatibles.
