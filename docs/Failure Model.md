# Failure Model

## Version
0.1.0

## Scope

Este documento define el modelo de fallos soportados por el cluster.

Describe:

- tipos de fallo asumidos
- comportamiento esperado del sistema
- límites del modelo
- respuestas del runtime

El objetivo es garantizar que el sistema sea robusto bajo fallos reales
de hardware, red y procesos.

---

# 1. PRINCIPIO GENERAL

El cluster está diseñado bajo el supuesto de que:

> Los fallos son normales, no excepcionales.

Por lo tanto:

- el sistema debe seguir funcionando parcialmente en fallo
- la degradación es preferible a la inconsistencia
- la recuperación es automática

---

# 2. TIPOS DE FALLO SOPORTADOS

## 2.1 NODE CRASH (fallo de proceso)

### Definición

El nodo se detiene abruptamente:

- proceso muere
- máquina se apaga
- watchdog falla
- SIGKILL / crash inesperado

### Efectos

- nodo deja de enviar heartbeat
- lease expira automáticamente
- estado pasa a OFFLINE o DEGRADED (según detección)

### Respuesta del sistema

- detección por expiración de lease
- reevaluación de liderazgo
- promoción automática de STANDBY

### Invariante asociado

> El sistema debe sobrevivir a la pérdida total de un nodo ACTIVE.

---

## 2.2 LEASE LOSS (pérdida de autoridad)

### Definición

El nodo pierde su lease sin necesariamente fallar:

- expiración TTL
- falta de renovación heartbeat
- conflicto de autoridad
- invalidación explícita

### Efectos

- nodo pierde derecho a escribir
- nodo deja de ser ACTIVE
- transición obligatoria a DEGRADED o STANDBY

### Respuesta del sistema

- eliminación de autoridad
- elección de nuevo líder
- propagación de cluster_view actualizado

### Invariante asociado

> Ningún nodo sin lease válido puede escribir.

---

## 2.3 NETWORK DELAY (latencia o degradación de red)

### Definición

La red introduce retrasos arbitrarios:

- heartbeat retrasado
- mensajes fuera de orden
- jitter alto
- latencia variable

### Efectos

- posibles expiraciones falsas de lease
- sospecha de fallo de nodo activo
- reevaluación prematura de liderazgo

### Respuesta del sistema

- tolerancia temporal en lease TTL
- uso de buffers de verificación
- evitación de promoción inmediata
- preferencia por estabilidad antes que failover

### Invariante asociado

> La red puede ser lenta, pero no debe causar split-brain estable.

---

## 2.4 NETWORK PARTITION (partición lógica de red)

### Definición

El cluster se divide en subgrupos aislados:

- nodos no se ven entre sí
- cluster view fragmentada
- comunicación parcial o nula

### Efectos

- múltiples candidatos a ACTIVE
- riesgo de split-brain
- pérdida de consenso global

### Respuesta del sistema

- detección de falta de quorum implícito
- degradación a STANDBY en nodos inciertos
- resolución determinista al reconectar
- prioridad a seguridad sobre disponibilidad

### Regla clave

> En caso de duda de autoridad → NO se permite ACTIVE.

### Invariante asociado

> Nunca debe existir más de un ACTIVE estable tras reconexión.

---

# 3. MODOS DE FALLA COMBINADOS

El sistema debe soportar combinaciones:

- crash + partition
- delay + lease loss
- network instability + recovery cycles

El comportamiento debe seguir siendo determinista.

---

# 4. MODOS DE DEGRADACIÓN

Cuando el sistema no puede garantizar consistencia:

- DEGRADED state se activa
- escritura se bloquea o limita
- liderazgo se suspende

Esto evita corrupción silenciosa.

---

# 5. PRINCIPIO DE RECUPERACIÓN

La recuperación siempre sigue este flujo:

1. detectar fallo
2. invalidar autoridad si existe duda
3. limpiar lease
4. reevaluar cluster view
5. elegir nuevo ACTIVE
6. estabilizar estado

---

# 6. INVARIANTES GLOBALES

## Invariante 1

El sistema debe converger eventualmente a:

- 1 ACTIVE válido
- N STANDBY sincronizados

---

## Invariante 2

No existe escritura sin lease válido.

---

## Invariante 3

La partición de red nunca puede producir autoridad permanente dual.

---

## Invariante 4

Todo fallo debe ser observable en cluster_view.

---

# 7. OBJETIVO DEL MODELO

Este modelo garantiza:

- tolerancia a fallos reales de infraestructura
- auto-recuperación sin intervención humana
- consistencia eventual del cluster
- prevención de corrupción silenciosa
