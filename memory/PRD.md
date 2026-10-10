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

## Backlog
- P0: Conectar WhatsApp Cloud API real (token + phone number id por empresa); pasarela Recurrente; FEL con INFILE/Digifact.
- P1: Cobro de anticipos a clientes finales (sección 7); emails reales (Resend); subdominio por empresa; object storage para archivos.
- P2: Google Calendar/Outlook, Power BI, Meta Ads; SMS; drag & drop en agenda; backups automatizados documentados.

## Next tasks
Integrar WhatsApp real y la pasarela cuando el usuario tenga las credenciales.
