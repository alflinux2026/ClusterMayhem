Aquí tienes el documento consolidado para seguimiento técnico y estratégico del proyecto.

# GeoMayhem / Mayhem Platform

## Documento Maestro de Planificación y Arquitectura

### Fecha: Mayo 2026

---

# 1. Visión General

El proyecto evoluciona desde un sistema de cluster distribuido hacia una plataforma backend reusable para múltiples aplicaciones realtime.

La idea no es construir únicamente una aplicación concreta, sino una infraestructura reusable sobre la que montar:

* GeoMayhem
* Tracking familiar
* Chat realtime
* Dietas y sincronización
* Sistemas colaborativos
* Apps geolocalizadas
* Servicios distribuidos

---

# 2. Concepto Central

## Arquitectura objetivo

```text
Mayhem Platform
    ├── Cluster Core
    ├── Identity/Auth
    ├── Event Bus
    ├── Realtime Messaging
    ├── Presence System
    ├── GeoTracking
    ├── Notifications
    ├── Sync Engine
    ├── Storage
    └── Application Services
```

---

# 3. Mayhem Cluster

## Objetivo

Crear un runtime/backend distribuido ligero orientado a:

* routing distribuido
* failover
* realtime
* sincronización
* coordinación de servicios

---

# 4. Estado Actual del Cluster

Actualmente ya existen conceptos/prototipos relacionados con:

* nodos cluster
* forwarding de eventos
* leader awareness
* cluster health
* retries
* event IDs
* failover conceptual
* routing entre nodos

---

# 5. Roadmap Cluster

# FASE 1 — Cluster Mínimo Funcional

## Objetivo

Cluster usable para servicios básicos.

## Funcionalidades

* node discovery
* leader election
* health checks
* event routing
* event forwarding
* retries
* gateway
* logging distribuido
* heartbeat
* APIs internas

## Tiempo estimado

2 a 6 semanas.

---

# FASE 2 — Robustez Distribuida

## Objetivo

Cluster estable ante fallos reales.

## Funcionalidades

* replicación
* recovery
* persistence
* node rejoin
* sincronización de estado
* colas distribuidas
* backpressure
* métricas
* observabilidad
* recuperación parcial
* split-brain prevention básico

## Tiempo estimado

1 a 3 meses.

---

# FASE 3 — Plataforma Distribuida

## Objetivo

Convertir el cluster en infraestructura reusable.

## Funcionalidades

* auth integration
* service registry
* distributed presence
* notifications
* media/events
* SDK
* APIs públicas
* realtime platform
* módulos reutilizables

## Tiempo estimado

3 a 12 meses.

---

# 6. Filosofía Arquitectónica

## Principio importante

Separar:

```text
infraestructura distribuida
```

de:

```text
business logic
```

---

# 7. Sistema de Usuarios / Auth

## Objetivo

Crear un servicio de identidad reusable e independiente.

Debe ser completamente agnóstico respecto a la aplicación final.

---

# 8. Arquitectura Auth

## Servicio independiente

```text
auth-service
```

Responsable de:

* usuarios
* passwords
* login
* refresh tokens
* sesiones
* verificación email
* recuperación password
* MFA futuro

---

# 9. Tecnologías Recomendadas

## Backend

* FastAPI
* PostgreSQL
* SQLAlchemy
* Pydantic
* Passlib
* PyJWT

---

# 10. Funcionalidades MVP Auth

## Primera versión

* registro email/password
* login
* JWT
* refresh token
* email verification
* reset password
* sesiones básicas
* logout

---

# 11. Seguridad

## Passwords

Nunca almacenar passwords en texto plano.

Usar:

* Argon2 (preferido)
* bcrypt

---

# 12. Arquitectura Tokens

## Access Token

JWT corto:

* 15-30 min

## Refresh Token

Persistente:

* 30 días aprox.

---

# 13. Flujo Registro

```text
usuario
    ↓
registro
    ↓
email verification
    ↓
cuenta activada
```

---

# 14. Integración con Cluster

Inicialmente:

```text
cluster consume JWT
```

Más adelante:

* sesiones distribuidas
* invalidación global
* auth replication
* distributed identity

---

# 15. Roadmap Auth

# FASE 1 — Núcleo Auth

## Tiempo estimado

3 a 7 días.

## Funcionalidades

* users
* login
* JWT
* refresh
* verify email
* reset password

---

# FASE 2 — Auth Sólido

## Tiempo estimado

1 a 3 semanas.

## Funcionalidades

* rate limiting
* sesiones
* logs
* Docker
* tests
* arquitectura modular
* integración cluster-ready

---

# FASE 3 — Identity Platform

## Tiempo estimado

1 a 3 meses.

## Funcionalidades

* MFA
* OAuth
* roles
* permisos
* auditoría
* admin panel
* WebAuthn/passkeys

---

# 16. GeoMayhem

## Concepto

Aplicación realtime basada sobre Mayhem Platform.

---

# 17. Objetivo GeoMayhem

Aplicación tipo:

* tracking familiar
* localización realtime
* rutas
* presencia
* grupos
* chat
* mapas colaborativos

---

# 18. Arquitectura GeoMayhem

```text
GeoMayhem
    ├── Frontend Mobile
    ├── Frontend Web
    ├── Backend APIs
    ├── Realtime Layer
    ├── Geo Engine
    ├── Chat
    └── Mayhem Platform
```

---

# 19. Componentes GeoMayhem

## Backend

* APIs REST
* WebSockets
* realtime
* tracking
* chat
* grupos

## Frontend

* mapas
* markers realtime
* rutas
* estados online
* chat UI

---

# 20. Roadmap GeoMayhem

# FASE 1 — MVP Tracking

## Funcionalidades

* login
* grupos
* tracking GPS
* mapa realtime
* markers
* perfiles básicos

## Tiempo estimado

1 a 3 meses.

---

# FASE 2 — Comunicación

## Funcionalidades

* chat realtime
* historial posiciones
* eventos
* presencia
* notificaciones

## Tiempo estimado

1 a 2 meses.

---

# FASE 3 — Plataforma Completa

## Funcionalidades

* cluster robusto
* replicación
* multimedia
* SDK
* panel administración
* múltiples apps

## Tiempo estimado

6 a 24 meses.

---

# 21. Complejidades Reales

## Lo difícil no es:

```text
que funcione
```

## Lo difícil es:

```text
que funcione siempre
```

---

# 22. Problemas Distribuidos Reales

* race conditions
* duplicados
* particiones de red
* nodos lentos
* reconexiones
* inconsistencias
* recovery
* clocks distintos
* split-brain

---

# 23. Filosofía de Desarrollo

## Construcción incremental

Primero:

```text
minimal distributed core
```

Luego:

* robustez
* sincronización
* plataforma reusable

---

# 24. Estrategia Recomendada

NO intentar construir desde el inicio:

* Life360 completo
* WhatsApp completo
* Google Maps completo

---

# 25. Objetivo Inteligente

Construir:

```text
infraestructura reusable
```

sobre la que luego puedan montarse múltiples aplicaciones.

---

# 26. Estimaciones Globales

## Cluster usable

1-2 meses.

## Cluster sólido

3-6 meses.

## Plataforma madura

1-2 años.

---

# 27. Estimaciones Auth

## MVP usable

3-7 días.

## Sistema sólido

2-4 semanas.

## Identity platform

varios meses.

---

# 28. Estimaciones GeoMayhem

## MVP usable

4-9 meses.

## Producto sólido

~1 año.

## Plataforma madura

2+ años.

---

# 29. Conclusión Estratégica

El verdadero valor del proyecto no es únicamente GeoMayhem.

El valor real está en construir:

```text
Mayhem Platform
```

como infraestructura reusable para aplicaciones distribuidas realtime.

Una vez existan:

* cluster
* auth
* realtime
* mapas
* eventos
* presencia
* chat

el núcleo de muchísimas aplicaciones modernas ya estará construido.
