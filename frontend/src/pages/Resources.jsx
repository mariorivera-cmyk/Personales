import { useAuth } from "@/context/Auth";
import CrudPage from "@/components/CrudPage";
import { money, DAYS } from "@/lib/api";

const yes = (v) => (v === false ? "No" : "Sí");

export function Services() {
  return (
    <CrudPage title="Servicios" subtitle="Catálogo, duración, precios, anticipos y estilistas autorizados" endpoint="/services" testid="services"
      defaults={{ duration: 60, price: 0, prep_minutes: 0, cleanup_minutes: 10, deposit: 0, active: true }}
      fields={[
        { key: "name", label: "Nombre" }, { key: "category", label: "Categoría" }, { key: "description", label: "Descripción", type: "textarea" },
        { key: "duration", label: "Duración (min)", type: "number" }, { key: "price", label: "Precio", type: "number" },
        { key: "deposit", label: "Anticipo fijo (0 = según reglas)", type: "number" }, { key: "cost", label: "Costo (para rentabilidad)", type: "number" },
        { key: "prep_minutes", label: "Preparación (min)", type: "number" }, { key: "cleanup_minutes", label: "Limpieza posterior (min)", type: "number" },
        { key: "rebook_days", label: "Recomendar retoque cada (días)", type: "number" }, { key: "active", label: "Activo", type: "switch" },
        { key: "stylist_ids", label: "Estilistas autorizados (vacío = todos)", type: "multi", source: "/stylists" },
      ]}
      columns={[
        { key: "name", label: "Servicio" }, { key: "category", label: "Categoría" }, { key: "duration", label: "Duración", render: (r) => `${r.duration} min` },
        { key: "price", label: "Precio", render: (r) => money(r.price) }, { key: "times", label: "Prep/Limpieza", render: (r) => `${r.prep_minutes || 0}/${r.cleanup_minutes || 0} min` },
        { key: "active", label: "Activo", render: (r) => yes(r.active) },
      ]} />
  );
}

export function Branches() {
  return (
    <CrudPage title="Sucursales" subtitle="Horarios de operación y capacidad operativa" endpoint="/branches" testid="branches"
      defaults={{ capacity: 4, hours: { 0: ["09:00", "19:00"], 1: ["09:00", "19:00"], 2: ["09:00", "19:00"], 3: ["09:00", "19:00"], 4: ["09:00", "19:00"], 5: ["09:00", "17:00"] } }}
      fields={[
        { key: "name", label: "Nombre" }, { key: "phone", label: "Teléfono" }, { key: "address", label: "Dirección", full: true },
        { key: "capacity", label: "Capacidad simultánea (citas)", type: "number" }, { key: "hours", label: "Horario de operación", type: "hours" },
      ]}
      columns={[
        { key: "name", label: "Sucursal" }, { key: "address", label: "Dirección" }, { key: "capacity", label: "Capacidad" },
        { key: "hours", label: "Días abiertos", render: (r) => Object.keys(r.hours || {}).map((d) => DAYS[d]).join(", ") },
      ]} />
  );
}

export function Stylists() {
  const { user } = useAuth();
  return (
    <CrudPage title="Estilistas" subtitle="Horarios laborales, especialidades y sucursal asignada" endpoint="/stylists" testid="stylists"
      defaults={{ active: true, hours: {}, branch_id: user.role === "branch_manager" ? user.branch_id : undefined }}
      fields={[
        { key: "name", label: "Nombre" }, { key: "branch_id", label: "Sucursal", type: "select", source: "/branches" },
        { key: "specialties", label: "Especialidades", full: true }, { key: "photo", label: "Foto (URL)" }, { key: "active", label: "Activo", type: "switch" },
        { key: "hours", label: "Horario laboral", type: "hours", optional: true },
      ]}
      columns={[
        { key: "name", label: "Estilista" }, { key: "specialties", label: "Especialidades" },
        { key: "hours", label: "Horario", render: (r) => (Object.keys(r.hours || {}).length ? "Propio" : "Sucursal") }, { key: "active", label: "Activo", render: (r) => yes(r.active) },
      ]} />
  );
}

export function Blocks() {
  return (
    <CrudPage title="Bloqueos y vacaciones" subtitle="Bloqueos manuales de agenda, vacaciones y capacitaciones" endpoint="/blocks" testid="blocks"
      defaults={{ reason: "Bloqueo" }}
      fields={[
        { key: "reason", label: "Tipo", type: "select", options: ["Bloqueo", "Vacaciones", "Capacitación", "Incapacidad"].map((x) => ({ value: x, label: x })) },
        { key: "stylist_id", label: "Estilista (vacío = toda la sucursal)", type: "select", source: "/stylists", placeholder: "Todos" },
        { key: "branch_id", label: "Sucursal (vacío = todas)", type: "select", source: "/branches", placeholder: "Todas" },
        { key: "start_date", label: "Desde", type: "date" }, { key: "end_date", label: "Hasta", type: "date" },
        { key: "start_time", label: "Hora inicio (vacío = día completo)", type: "time" }, { key: "end_time", label: "Hora fin", type: "time" },
        { key: "notes", label: "Notas", type: "textarea" },
      ]}
      columns={[
        { key: "reason", label: "Tipo" }, { key: "dates", label: "Fechas", render: (r) => `${r.start_date} → ${r.end_date}` },
        { key: "time", label: "Horario", render: (r) => (r.start_time ? `${r.start_time}-${r.end_time}` : "Día completo") }, { key: "notes", label: "Notas" },
      ]} />
  );
}

export function Waitlist() {
  return (
    <CrudPage title="Lista de espera" subtitle="Se notifica automáticamente por WhatsApp cuando se libera un espacio" endpoint="/waitlist" testid="waitlist"
      defaults={{}}
      fields={[
        { key: "phone", label: "Teléfono" }, { key: "name", label: "Nombre" },
        { key: "service_id", label: "Servicio", type: "select", source: "/services" }, { key: "branch_id", label: "Sucursal", type: "select", source: "/branches" },
        { key: "date", label: "Fecha deseada", type: "date" }, { key: "notes", label: "Notas", type: "textarea" },
        { key: "status", label: "Estado", type: "select", options: [{ value: "waiting", label: "En espera" }, { value: "notified", label: "Notificado" }, { value: "booked", label: "Agendado" }], hideIf: (f) => !f.id },
      ]}
      columns={[
        { key: "client_name", label: "Cliente" }, { key: "client_phone", label: "Teléfono" }, { key: "service_name", label: "Servicio" },
        { key: "date", label: "Fecha" }, { key: "status", label: "Estado", render: (r) => ({ waiting: "En espera", notified: `Notificado ${r.offered_time || ""}`, booked: "Agendado" }[r.status]) },
      ]} />
  );
}

export function UpsellRules() {
  return (
    <CrudPage title="Cross-selling y Upselling" subtitle="Reglas de recomendación aplicadas en WhatsApp, portal y recepción" endpoint="/rules" testid="rules"
      defaults={{ type: "cross", active: true }}
      fields={[
        { key: "type", label: "Tipo", type: "select", options: [{ value: "cross", label: "Cross-selling (complementario)" }, { value: "up", label: "Upselling (versión superior)" }] },
        { key: "trigger_service_id", label: "Servicio principal", type: "select", source: "/services" },
        { key: "suggested_service_id", label: "Servicio sugerido", type: "select", source: "/services" },
        { key: "message", label: "Mensaje / promoción", full: true }, { key: "active", label: "Activa", type: "switch" },
      ]}
      columns={[
        { key: "type", label: "Tipo", render: (r) => (r.type === "cross" ? "Cross-selling" : "Upselling") }, { key: "message", label: "Mensaje" },
        { key: "active", label: "Activa", render: (r) => yes(r.active) },
      ]} />
  );
}
