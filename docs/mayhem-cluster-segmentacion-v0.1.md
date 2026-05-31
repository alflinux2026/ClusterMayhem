# Mayhem-Cluster — Contrato de segmentación de logs y trabajo

## Objetivo

Definir una segmentación clara para evitar que los ficheros de trabajo crezcan indefinidamente y se vuelvan intratables. El sistema debe detectar cuándo un segmento ha llegado a su condición de cierre, marcar ese estado y ejecutar el sellado, la creación del siguiente segmento y la réplica del cerrado sin perder trazabilidad.

## Principio general

El nodo es la fuente de decisión.  
El estado del segmento no tiene una máquina propia: se deriva a partir de datos ya existentes, y el nodo decide qué hacer con ese valor usando sus helpers de transición.

- `node_state` y `segment_status` son independientes.
- El helper de segmento solo devuelve un valor de estado derivado.
- La transición del nodo la ejecuta el nodo.
- La operación física de sellado, apertura y réplica la ejecuta `segmentation.py`.

## Estados del nodo

El estado del nodo describe qué puede hacer el runtime en ese momento.

- `BOOT` y `DISCOVERING` son estados de preparación.
- `ACTIVE` permite recepción y despacho.
- `STANDBY` mantiene presencia y supervisa condiciones de segmentación.
- `SEGMENTATION` ejecuta la operación de cierre y creación de segmento.
- `DEGRADED`, `ISOLATED` y `OFFLINE` representan degradación o indisponibilidad.

## Estados del segmento

El estado del segmento describe el ciclo de vida del lote de trabajo actual.

- `running`: el segmento acepta trabajo.
- `size_completed`: el segmento ha alcanzado el tamaño objetivo.
- `draining`: el nodo ya no debe admitir nuevo trabajo para ese segmento.
- `drained`: todo el trabajo pendiente está `COMPLETED`.
- `ready_to_segment`: coinciden las condiciones para cerrar.
- `cloning`: el nodo está sellando y replicando el segmento.
- `cloned`: el segmento ya quedó finalizado.

## Criterio de decisión

El helper de segmento devuelve solo el estado derivado correspondiente.  
No hace transiciones, no muta el nodo y no ejecuta operaciones físicas.

El nodo compara el estado devuelto con su situación actual y, si corresponde, usa sus helpers de transición para mover el nodo a `SEGMENTATION`. A partir de ahí, `segmentation.py` hace el trabajo real.

## Secuencia funcional

1. El nodo consulta el helper de estado de segmento.
2. El helper devuelve un estado derivado.
3. El nodo evalúa si debe transicionar.
4. Si el estado exige cierre, el nodo pasa a `SEGMENTATION`.
5. `segmentation.py` sella el segmento actual.
6. `segmentation.py` abre el siguiente segmento.
7. `segmentation.py` replica el segmento cerrado.
8. El nodo vuelve al flujo normal.

## Responsabilidades por archivo

### `state.py`
Responsable de los estados del nodo y de la transición de estado del nodo.

- `NodeState`
- `ensure_state_meta(node, now=None)`
- `transition_node_state(node, new_state, reason=None, now=None)`
- `get_state_age_s(node, now=None)`

### `segment_status.py` o helper equivalente
Responsable de devolver un valor de estado derivado del segmento.

- Función pura o casi pura.
- Sin mutar el nodo.
- Sin transiciones.
- Sin sellado ni réplica.

### `segmentation.py`
Responsable de ejecutar la operación física de segmentación.

- Sellar el segmento actual.
- Abrir el siguiente segmento.
- Replicar el cerrado.
- Dejar el nodo listo para volver al flujo normal.

## Reglas de operación

- Un segmento no se cierra solo por estar en `STANDBY`.
- Un segmento no se cierra solo por haber llegado al tamaño objetivo.
- Un segmento no se cierra solo por estar drenado.
- Un segmento solo se cierra cuando el helper devuelve el estado adecuado y el nodo decide transicionar.
- El segmento cerrado queda inmutable para el flujo normal.

## Datos publicados por el nodo

El nodo publica estado operativo y datos auxiliares de supervisión.  
A esta capa se puede añadir `segment_status` para que el resto del cluster sepa en qué punto está el segmento sin tener que re-derivar la información.

## A validar

Queda por validar principalmente:

- El nombre definitivo del helper de estado de segmento.
- El campo exacto que expresa el tamaño actual del segmento.
- El umbral de sellado.
- Si `segment_status` viaja dentro del heartbeat o en una vista separada.
- Qué metadatos mínimos se usan para verificar la réplica de segmentos cerrados.

## Resultado esperado

Con esta separación, el nodo consulta un valor de estado derivado, decide si transicionar y ejecuta la segmentación física solo cuando toca. El código queda más claro, la rotación de segmentos queda centralizada y no aparece una FSM fantasma donde no pinta nada.

## Ajuste importante que yo cerraría

Hay una sutileza que conviene dejar explícita en el contrato para que no vuelva a romperse luego:

- `segment_status` no es una máquina de estados independiente.
- `segment_status` es un resultado derivado de evaluación.
- `SEGMENTATION` es un estado del nodo, no del segmento.
- El segmento solo tiene estados funcionales de ciclo de vida.

Eso evita la típica confusión de “estado del segmento vs estado del nodo”, que si no se documenta bien acaba en dos FSM peleándose por el mismo fichero como dos personas discutiendo por el mando de la tele.
