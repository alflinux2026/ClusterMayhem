# Lease + Election Rules

## Version
0.1.0

## Scope

Este documento formaliza las reglas de:

- concesión de lease
- expiración de lease
- elegibilidad de liderazgo
- elección de nodo ACTIVE
- resolución de conflictos (split-brain)

Aplica a todo el cluster runtime.

---

# 1. PRINCIPIO BASE

El liderazgo en el cluster no es fijo.

Es una propiedad temporal basada en:

- lease válido
- estado del nodo
- prioridad
- visibilidad del cluster
- consistencia de datos

---

# 2. DEFINICIÓN DE LEASE

Un lease es un contrato temporal de autoridad.

## Propiedades

- owner: node_id
- ttl: tiempo de vida
- created_at: timestamp

## Regla fundamental

Solo un nodo con lease válido puede ser ACTIVE.

---

# 3. CICLO DE VIDA DEL LEASE

## 3.1 Creación

Un lease se crea cuando:

- un nodo es promovido a ACTIVE
- el sistema valida elegibilidad
- no existe otro ACTIVE válido superior

## 3.2 Renovación

Solo el nodo ACTIVE puede:

- renovar su lease
- extender TTL
- reafirmar autoridad

## 3.3 Expiración

Un lease expira cuando:

- TTL se agota
- heartbeat falla
- nodo deja de renovar

Cuando esto ocurre:

- el nodo pierde autoridad inmediatamente
- el cluster debe iniciar reevaluación

---

# 4. REGLAS DE ELECCIÓN

## 4.1 Condiciones para ser candidato

Un nodo puede aspirar a ACTIVE si:

- estado == STANDBY o DISCOVERING
- datasets consistentes
- lease inválido o inexistente en cluster
- conectividad con cluster view suficiente

---

## 4.2 Condiciones obligatorias para ACTIVE

Un nodo SOLO puede ser ACTIVE si cumple:

- lease válido adquirido
- watchdog saludable
- datasets íntegros
- no existe ACTIVE superior visible
- cluster view consistente

---

## 4.3 Prioridad

La elección usa prioridad determinista:

- menor priority value = mayor prioridad
- empate → node_id más bajo gana

---

# 5. REGLAS DE TRANSICIÓN DE LIDERAZGO

## 5.1 STANDBY → ACTIVE

Permitido si:

- no hay ACTIVE válido
- lease puede ser adquirido
- nodo es el mejor candidato

---

## 5.2 ACTIVE → STANDBY

Obligatorio si:

- aparece nodo superior válido
- lease se pierde
- conflicto de autoridad detectado

---

## 5.3 ACTIVE → DEGRADED

Obligatorio si:

- lease expira
- corrupción detectada
- inconsistencia crítica
- watchdog falla

---

# 6. SPLIT-BRAIN RULES

## 6.1 Detección

Existe split-brain si:

- más de un nodo ACTIVE válido simultáneamente

---

## 6.2 Resolución

Se resuelve determinísticamente:

1. menor priority gana
2. si empate → menor node_id
3. los demás se degradan a STANDBY

---

## 6.3 Invariante crítico

El sistema debe converger a:

- exactamente 1 ACTIVE

en todos los casos posibles.

---

# 7. LEASE INVALIDATION RULES

Un lease se considera inválido si:

- TTL expirado
- nodo no emite heartbeat
- nodo cambia de estado a DEGRADED o OFFLINE
- conflicto de autoridad detectado

---

# 8. HEARTBEAT DEPENDENCY

El lease depende indirectamente de:

- heartbeat activo del nodo
- estabilidad del runtime loop

Sin heartbeat:

- lease expira naturalmente
- nodo pierde elegibilidad

---

# 9. SAFETY PRIORITY ORDER

El sistema siempre prioriza:

1. seguridad del cluster
2. consistencia de estado
3. disponibilidad

Nunca:

- disponibilidad antes que consistencia

---

# 10. INVARIANTES

Estos invariantes son estrictos:

- máximo 1 lease válido ACTIVE
- solo ACTIVE puede emitir lease
- lease expirado = pérdida inmediata de autoridad
- elección siempre determinista
- nodos nunca asumen ACTIVE sin validación completa

---

# 11. OBJETIVO FUNCIONAL

El sistema debe garantizar:

- elección automática de líder
- failover sin intervención humana
- recuperación tras fallo de nodo
- ausencia de split-brain estable
- convergencia eventual del cluster
