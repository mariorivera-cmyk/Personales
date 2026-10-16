# PRD — SalonFlow (SaaS de citas para salones de belleza con WhatsApp)

## Original problem statement
Solicitud de Desarrollo: Plataforma SaaS de Gestión de Citas para Salones de Belleza Integrada con WhatsApp — multiempresa, escalable; cada empresa con número de WhatsApp propio; deploy fácil; estado de cuenta de empresas; costo por módulo habilitable/deshabilitable; pagos mensuales/anuales con tarjeta. Secciones: 1 Arquitectura multi-tenant, 2 Citas por WhatsApp (consultar, reservar, modificar, cancelar, confirmar; validación de disponibilidad; alternativas), 3 Agenda inteligente, 4 Servicios, 5 CRM, 6 Recordatorios 48/24/2h, 7 Anticipos y pagos (pendiente), 8 Portal de reservas, 9 Fidelización, 10 Cross/Upselling, 11 Motor de recomendaciones, 12 Lista de espera, 13 Dashboard, 14 Reportería, 15 Roles, 16 Marketing, 17 Seguridad, 18 Integraciones deseables, 19 Facturación/Suscripciones SaaS (planes, módulos con precio, prorrateo, alta autoservicio, cobro recurrente, reintentos, morosidad y suspensión, estado de cuenta, FEL, pasarela GT, MRR/ARR/churn).

User choices: WhatsApp simulado en la plataforma; asistente IA Claude Sonnet 4.5 (Emergent key); login email/contraseña JWT; pasarela simulada (Recurrente después); todo lo posible en una versión.

## Architecture
- FastAPI (core.py auth/guards/tenant ctx, engine.py disponibilidad/reservas, billing.py SaaS, routes_saas/routes_ops/routes_wa, seed.py) + MongoDB (uuid ids) + React (CrudPage genérico, páginas por módulo).
- Multi-tenant por company_id; super admin actúa sobre empresa con header X-Company-Id. Módulos se validan en backend (guard mod=...).
- WhatsApp: POST /api/wa/inbound (simulador) y /api/wa/webhook (formato Meta Cloud API) enrutan por número de la empresa; Claude con ciclo de acciones JSON (availability/book/reschedule/cancel/confirm/waitlist).
- Scheduler asyncio: recordatorios cada 5 min, ciclo de cobro cada 6 h.
- API docs: /api/docs.

## Personas
Super Administrador, Administrador de Empresa, Gerente de Sucursal, Recepcionista, Estilista, Cliente final (WhatsApp / portal).

## Implemented (2026-10-10)
- Auth JWT + brute force, 5 roles, auditoría, notas CRM cifradas (Fernet), archivos de cliente (Mongo, ≤3MB).
- Sucursales/estilistas/servicios/bloqueos/festivos/capacidad; motor de slots con prep/limpieza; alternativas (otros horarios, estilistas, sucursales, días).
- Agenda día/semana/mes con ocupación por estilista y sucursal; CRM con historial/estadísticas; portal /b/:slug (reservar, reprogramar, cancelar, lista de espera, referidos).
- Recordatorios 48/24/2h, lista de espera con notificación al cancelar, fidelización (puntos, canje, membresías, cupones, referidos), reglas cross/upsell, recomendaciones de retoque, campañas (cumpleaños, inactivos, retoque, promo, recuperación).
- Dashboard y reportes (sucursal/estilista/servicio/cliente).
- SaaS: planes, módulos con precio, cupones, configuración (impuesto, moneda, descuento anual, prueba, gracia, reintentos, extras), alta autoservicio, toggles con prorrateo, facturas PDF, pagos tarjeta/transferencia con aprobación, morosidad → suspensión parcial/total → reactivación, estado de cuenta, export Excel, MRR/ARR/churn/conversión, costo WhatsApp.
- MOCKED: pasarela de pagos, FEL (certificador), envío real de WhatsApp/email/SMS.

## Implemented v2 (2026-10-15) — requerimientos_salonflow_v2 (R1–R20)
- R1 OTP 6 dígitos para "Mis citas" (hash, 10 min, 5 intentos→bloqueo 15 min, 3 envíos/h, sesión 30 min, respuesta uniforme).
- R2 Estados Atendida/No asistió/Cancelar con log; atendida solo la corrige admin; "Pendientes de cerrar" en dashboard.
- R3 Cobro en caja manual (efectivo/POS/transferencia/mixto, propina, descuento con motivo), Cierre de caja + Excel, anulación por admin (revierte puntos y stock).
- R4 Portal: descripción, logo/fotos (media), mapa, horarios, equipo, redes, lang=es, título con nombre.
- R5 Política de cancelación, anticipo manual con datos bancarios, "Anticipo recibido", liberación automática, cancelación tardía, alerta/anticipo forzado por faltas.
- R6 Diálogo de cancelación con motivo, mensajes vacíos con "Crear el primero", loaders, "Hoy ya no hay turnos".
- R7 Guía de arranque + QR; plantillas de servicios. R8 Registro de 4 campos + slug con sugerencias; activación con NIT/tarjeta y total con IVA; aviso fin de prueba.
- R9 Multi-servicio con estilista por servicio y horarios seguidos; foto, "Desde", pausas. R10 Recordatorios con plantilla, dirección, enlace, fallback a correo.
- R11 Comisiones (%/fijo/sueldo/propinas) + Excel. R12 Ficha técnica: alergias, fórmulas, consentimiento de fotos, antes/después, alertas, auditoría de acceso.
- R13 Agenda con colores/leyenda, drag & drop, búsqueda de clienta. R14 Selector de país, validaciones, textos de ayuda, pasos, barra móvil.
- R15 Cuenta cliente (historial, Repetir, puntos, solicitud de borrado). R16 Reseñas por enlace + galería + moderación + aviso calificación baja.
- R17 Inventario, venta mostrador, consumo por servicio, alertas. R18 Google Calendar + .ics. R19 Pie con términos/privacidad editables. R20 Alerta sucursal sin dirección.

## Implemented R21 (2026-10-16) — Panel de reglas del salón
- backend/rules.py: 42 reglas (grupos A–F) con valor sugerido único (ajustable por país), general + por sucursal (herencia), validación con mensajes claros, auditoría antes→después, restaurar sugeridos, solo admin edita. API /api/salon-rules (upsell sigue en /api/rules).
- Cada cita guarda copia de reglas (appointments.rules); cancelación tardía, reprogramación, recordatorios y reembolso usan esa copia.
- Aplicadas en: horarios (intervalo, limpieza, anticipación mín/máx solo en línea), anticipo (condiciones, % o fijo, plazo, datos bancarios, reembolso), faltas (periodo, límite, alerta/anticipo/bloqueo, tolerancia), máx citas activas, comisiones (modelo, %, propinas, periodo), puntos, recordatorios (horas, canal, alternativa), portal (/quote), confirmaciones y asistente WhatsApp.
- Pestaña Configuración › Reglas del salón; paso en guía de arranque. Probado: iteration_3 (24 tests backend + UI).

## Implemented D1–D10 (2026-10-16) — detalles_segunda_prueba
- D1 teléfonos de 8 dígitos se normalizan a +502 (OTP aparece en simulador). D2 no se puede marcar Atendida/cobrar antes de la hora de inicio. D3 cancelación desde panel: vista previa (tardía, consecuencia, reembolso), casilla "aplicar política", tipo de cancelación guardado, aviso WhatsApp a la clienta, contador de tardías en ficha; no se puede re-cancelar.
- D4 texto "Hoy ya no hay turnos". D5 título "Reserva pendiente de anticipo" + plazo. D6 comisiones por fecha de cobro y rango del periodo completo + mensaje vacío. D7 aviso "Existencia baja: Nombre (x/min)". D8 enlace del registro respetado / sugerencias. D9 producto nuevo aparece en venta sin recargar. D10 advertencia precio < costo.
- Probado: iteration_4.

## Implemented (2026-10-16) — Categorías, servicios por estilista, plantillas
- Categorías de servicio administrables (crear, renombrar → actualiza servicios, eliminar solo si no se usan; sin duplicados). Campo Categoría del servicio ahora es selección. Se importan automáticamente las existentes; las plantillas crean las que falten.
- Estilistas: campo "Servicios que realiza" (varios). Disponibilidad filtra por él; si el servicio tenía lista de autorizados, se agrega la estilista automáticamente.
- Checkboxes más grandes en plantillas y selecciones múltiples (etiqueta clicable). Probado: iteration_5 + verificación de correcciones.

## Implemented (2026-10-16) — Arranque obligatorio para salones nuevos
- Mientras no se completen los 4 pasos obligatorios (servicios, estilistas, datos del salón + direcciones, reglas), el menú muestra solo Dashboard, Servicios, Sucursales, Estilistas, Configuración y Mi suscripción; otras rutas redirigen; portal público y bot de WhatsApp quedan en pausa. Al terminar se marca setup_complete (permanente) y se desbloquea al instante.
- "Guardar y confirmar reglas" permite aceptar las reglas sugeridas. Salones existentes completos se marcaron automáticamente. Probado: iteration_6 y 7.

## Backlog
- P0: Conectar WhatsApp Cloud API real (token + phone number id por empresa); pasarela Recurrente; FEL con INFILE/Digifact.
- P1: Cobro de anticipos a clientes finales (sección 7); emails reales (Resend); subdominio por empresa; object storage para archivos.
- P2: Google Calendar/Outlook, Power BI, Meta Ads; SMS; drag & drop en agenda; backups automatizados documentados.

## Next tasks
Integrar WhatsApp real y la pasarela cuando el usuario tenga las credenciales.
