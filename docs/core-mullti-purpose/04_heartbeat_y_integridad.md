# Culter Multi Purpose — Heartbeat e integridad

## Qué debe anunciar el heartbeat
- Identidad del nodo.
- Estado operativo.
- Prioridad.
- Metadata del log local.
- Integridad del cluster.
- Resumen por stream.

## Campos recomendados
```python
{
    "node_id": "lnx203hp",
    "state": "ACTIVE",
    "priority": 203,
    "ts": 1716400000.0,
    "log_meta": {
        "dirty": False,
        "last_append_event_id": "evt-123",
        "last_append_created_at": 1716400000.0,
        "log_size": 1583038,
        "file_size": 1583038,
        "file_hash": "abc123..."
    },
    "cluster_integrity": {
        "integrity_ok": True,
        "alivenodes": ["lnx200nas", "lnx202pc", "lnx203hp"]
    },
    "streams": {
        "tenantA.appFoo.telemetry.v1": {
            "active_segment_id": "000003",
            "active_segment_size": 1583038,
            "last_sealed_segment_id": "000002",
            "last_sealed_segment_hash": "def456...",
            "dirty": True
        }
    }
}
```

## Reglas
- Solo se replican segmentos sellados.
- El segmento activo puede cambiar.
- Lo sellado no cambia.
- El hash debe calcularse sobre el fichero final.

## Objetivo
Permitir que el cluster compare estados por stream y no solo por nodo.
