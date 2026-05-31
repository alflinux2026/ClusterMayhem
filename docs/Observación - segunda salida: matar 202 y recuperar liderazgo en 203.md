## Observación - segunda salida: matar 202 y recuperar liderazgo en 203

### Escenario
Después de una fase previa con alternancia de leader, se fuerza nueva transición de liderazgo:
- 202 cae
- 203 recupera liderazgo
- se observa el comportamiento local de 203 tras volver a `ACTIVE`

### Evidencia observada
En 203 aparecen ejecuciones y completados locales:

- `msg-203: 188 -> EXECUTING -> COMPLETED`
- `msg-203: 189 -> EXECUTING -> COMPLETED`
- `msg-203: 177 -> EXECUTING -> COMPLETED`
- `msg-203: 185 -> EXECUTING -> COMPLETED`

Después, el visor queda estable:

```text
[EVENT STATE] leader=lnx203hp latest(c=0,e=0,d=15) raw(c=29,e=29,d=15) raw_total=73 latest_total=15
```

y vuelve a repetirse igual unos segundos después, sin más progreso pendiente.

### Interpretación
Cuando 203 vuelve a ser leader:
- sí es capaz de drenar y completar los eventos locales que tenía pendientes
- no parece quedarse con `CREATED` o `EXECUTING` residuales en su vista local
- su estado local converge a `c=0,e=0,d=15`

### Conclusión
La segunda transición (matar 202 y devolver liderazgo a 203) sugiere que:

- 203 **sí puede recuperar y cerrar su backlog local** al volver a ser leader
- el problema no parece ser que 203 no sepa retomar eventos al recuperar liderazgo
- el `EVENT STATE` de 203 sigue siendo **estado local**, no estado global del cluster

### Hallazgo importante
Aunque el cluster global hubiera procesado muchos más eventos, el log de 203 termina en:

- `latest_total=15`
- `d=15`

Eso indica que `event_log.local.jsonl` representa solo la historia local del nodo, no la integridad total del cluster.

### Implicación práctica
El visor actual debería separarse conceptualmente en dos niveles:

- `LOCAL EVENT STATE`: estado del journal local del nodo
- `CLUSTER EVENT STATE`: estado agregado entre nodos o calculado sobre una fuente común de verdad

### Resumen corto
- matar 202 y promocionar 203 **no deja basura local pendiente**
- 203 drena lo suyo y se estabiliza bien
- lo que falta ahora no es tanto handoff local en este caso, sino **agregación multi-nodo** para validar integridad global del cluster
