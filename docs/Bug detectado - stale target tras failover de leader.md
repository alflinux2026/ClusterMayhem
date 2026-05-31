## Bug detectado - stale target tras failover de leader

### Síntoma
Cuando un nodo nuevo asume liderazgo y recupera eventos atascados en `EXECUTING`, algunos eventos siguen intentando ejecutarse contra el `targetnode` anterior aunque ese nodo ya esté caído.

Caso observado:
- `lnx202pc` pasa a `ACTIVE`.
- Aparece `DISPATCH` de varios eventos pendientes.
- Los eventos se marcan `EXECUTING`.
- `WORKER SEND` sigue apuntando a `lnx200nas`.
- `WORKER SEND FAIL` devuelve `connection refused` porque `lnx200nas` está muerto.
- El reconciler detecta `EXECUTING STUCK -> CREATED`.
- En el siguiente tick vuelve a ocurrir el mismo ciclo una o más veces.
- Finalmente, más tarde, el dispatch recalcula y envía a `lnx202pc`, donde completa correctamente.

### Diagnóstico
El reconciler **sí rescata** eventos atascados, pero la reasignación de destino no es suficientemente agresiva.

Problema probable:
- `targetnode` queda stale tras el failover.
- El `alive set` del dispatcher tarda en converger o sigue considerando válido al nodo muerto.
- Al pasar `EXECUTING -> CREATED`, el evento vuelve a entrar en dispatch pero puede reciclar el mismo target muerto.

### Evidencia observada
Patrón repetido:
1. `EVENT -> EXECUTING node=lnx200nas`
2. `WORKER SEND FAIL ... connection refused`
3. `RECONCILER: EXECUTING STUCK -> CREATED`
4. nuevo `DISPATCH`
5. otra vez `EXECUTING node=lnx200nas`
6. más tarde, por fin `WORKER SEND -> lnx202pc`
7. `COMPLETED`

### Impacto
- No rompe necesariamente la entrega final.
- Sí introduce retries inútiles.
- Puede degradar bastante bajo más carga o con más fallos simultáneos.
- Puede generar pequeños bucles `EXECUTING -> CREATED -> EXECUTING` contra nodos muertos.

### Fix esperado
Al reconciliar un evento `EXECUTING` atascado:

- limpiar `targetnode`
- forzar reasignación completa en el próximo dispatch
- excluir nodos con fallo reciente o `lastseen` stale
- revisar incremento correcto de `attempt`
- opcional: marcar `routehops += reconciler-force-reassign`

### Secuencia deseada
1. Evento estaba en `EXECUTING` sobre nodo muerto.
2. Nuevo leader detecta que está atascado.
3. Reconciler hace `EXECUTING -> CREATED`.
4. También limpia `targetnode`.
5. Dispatcher recalcula `alive`.
6. Selecciona worker realmente vivo.
7. Ejecuta y completa.

### Ticket sugerido
**Título:** Reassignment after leader failover can retry EXECUTING events on dead target node

**Resumen:**
Tras cambio de leader, eventos recuperados desde `EXECUTING` pueden redispatcharse repetidamente al worker caído antes de reubicarse en un nodo vivo.

**Causa probable:**
`targetnode` stale y/o selección `alive` retrasada en dispatcher tras failover.

**Arreglo esperado:**
Limpiar `targetnode` al hacer recovery, y evitar workers stale o con fallo reciente en la nueva selección.
