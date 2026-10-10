import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg, ROLES } from "@/lib/api";
import { useAuth } from "@/context/Auth";
import { PageHeader, Panel, Label } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import CrudPage from "@/components/CrudPage";

function General() {
  const { company, refresh } = useAuth();
  const [f, setF] = useState(company);
  const s = f.settings || {};
  const setS = (k, v) => setF({ ...f, settings: { ...s, [k]: v } });
  const save = async () => {
    try { await api.put("/company", f); toast.success("Configuración guardada"); refresh(); } catch (e) { toast.error(errMsg(e)); }
  };
  const rule = (s.deposit_rules || [])[0] || {};
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Panel title="Empresa y WhatsApp">
        <div className="space-y-3">
          {[["name", "Nombre comercial"], ["phone", "Teléfono"], ["whatsapp_number", "Número de WhatsApp Business (identifica a la empresa)"], ["slug", "Enlace del portal"]].map(([k, l]) => (
            <div key={k}><Label>{l}</Label><input className="field" value={f[k] || ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} data-testid={`settings-${k}-input`} /></div>
          ))}
          <p className="text-xs text-muted-foreground">Portal público: {window.location.origin}/b/{f.slug}</p>
          <div><Label>Frase del portal</Label><input className="field" value={s.portal?.tagline || ""} onChange={(e) => setS("portal", { ...s.portal, tagline: e.target.value })} data-testid="settings-tagline-input" /></div>
        </div>
      </Panel>
      <Panel title="Reglas de agenda y automatización">
        <div className="space-y-3">
          <div><Label>Días festivos (YYYY-MM-DD separados por coma)</Label>
            <input className="field" value={(s.holidays || []).join(", ")} onChange={(e) => setS("holidays", e.target.value.split(",").map((x) => x.trim()).filter(Boolean))} data-testid="settings-holidays-input" /></div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Anticipo obligatorio desde (min)</Label><input type="number" className="field" value={rule.min_minutes ?? ""} onChange={(e) => setS("deposit_rules", [{ ...rule, min_minutes: Number(e.target.value) }])} data-testid="settings-deposit-min" /></div>
            <div><Label>% de anticipo</Label><input type="number" className="field" value={rule.percent ?? ""} onChange={(e) => setS("deposit_rules", [{ ...rule, percent: Number(e.target.value) }])} data-testid="settings-deposit-pct" /></div>
          </div>
          <div><Label>Recordatorios (horas antes, separados por coma)</Label>
            <input className="field" value={(s.reminder_hours || []).join(", ")} onChange={(e) => setS("reminder_hours", e.target.value.split(",").map((x) => Number(x.trim())).filter(Boolean))} data-testid="settings-reminders-input" /></div>
          <div><Label>Mensaje para clientes si la cuenta está suspendida</Label>
            <textarea className="field h-20 py-2" value={s.suspension_message || ""} onChange={(e) => setS("suspension_message", e.target.value)} data-testid="settings-suspension-msg" /></div>
        </div>
      </Panel>
      <div className="lg:col-span-2"><Button onClick={save} data-testid="settings-save-btn">Guardar configuración</Button></div>
    </div>
  );
}

function Audit() {
  const [rows, setRows] = useState([]);
  useEffect(() => { api.get("/audit").then((r) => setRows(r.data)); }, []);
  return (
    <div className="overflow-x-auto rounded-2xl border bg-white">
      <table className="w-full text-sm" data-testid="audit-table">
        <thead className="bg-secondary/60 text-left text-xs uppercase text-slate-500"><tr><th className="px-4 py-3">Fecha</th><th className="px-4 py-3">Usuario</th><th className="px-4 py-3">Acción</th><th className="px-4 py-3">Entidad</th><th className="px-4 py-3">Detalle</th></tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={r.id} className="border-t"><td className="px-4 py-2 text-xs">{r.created_at.slice(0, 19).replace("T", " ")}</td><td className="px-4 py-2">{r.user_email}</td><td className="px-4 py-2">{r.action}</td><td className="px-4 py-2">{r.entity}</td><td className="max-w-xs truncate px-4 py-2 text-xs text-muted-foreground">{r.detail}</td></tr>
        ))}</tbody>
      </table>
    </div>
  );
}

export default function CompanySettings() {
  return (
    <div data-testid="settings-page">
      <PageHeader title="Configuración" subtitle="Empresa, usuarios y trazabilidad" />
      <Tabs defaultValue="general">
        <TabsList className="mb-6"><TabsTrigger value="general" data-testid="tab-general">General</TabsTrigger><TabsTrigger value="users" data-testid="tab-users">Usuarios y roles</TabsTrigger><TabsTrigger value="audit" data-testid="tab-audit">Auditoría</TabsTrigger></TabsList>
        <TabsContent value="general"><General /></TabsContent>
        <TabsContent value="users">
          <CrudPage embedded endpoint="/users" testid="users" defaults={{ role: "receptionist", active: true }}
            fields={[
              { key: "name", label: "Nombre" }, { key: "email", label: "Correo", type: "email" }, { key: "password", label: "Contraseña (dejar vacío para no cambiar)", type: "password" },
              { key: "role", label: "Rol", type: "select", options: ["company_admin", "branch_manager", "receptionist", "stylist"].map((v) => ({ value: v, label: ROLES[v] })) },
              { key: "branch_id", label: "Sucursal (gerente/estilista)", type: "select", source: "/branches" },
              { key: "stylist_id", label: "Perfil de estilista vinculado", type: "select", source: "/stylists" }, { key: "active", label: "Activo", type: "switch" },
            ]}
            columns={[{ key: "name", label: "Nombre" }, { key: "email", label: "Correo" }, { key: "role", label: "Rol", render: (r) => ROLES[r.role] }, { key: "active", label: "Activo", render: (r) => (r.active === false ? "No" : "Sí") }]} />
        </TabsContent>
        <TabsContent value="audit"><Audit /></TabsContent>
      </Tabs>
    </div>
  );
}
