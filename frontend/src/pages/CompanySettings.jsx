import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg, ROLES } from "@/lib/api";
import { useAuth } from "@/context/Auth";
import { PageHeader, Panel, Label } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { useSearchParams } from "react-router-dom";
import CrudPage, { FieldInput } from "@/components/CrudPage";
import { SalonRules } from "@/components/SalonRules";

function General() {
  const { company, refresh, checkSetup } = useAuth();
  const [f, setF] = useState(company);
  const s = f.settings || {};
  const setS = (k, v) => setF({ ...f, settings: { ...s, [k]: v } });
  const save = async () => {
    try { await api.put("/company", f); toast.success("Configuración guardada"); await refresh(); checkSetup(); } catch (e) { toast.error(errMsg(e)); }
  };
  const legal = s.legal || {};
  const social = f.social || {};
  const photos = f.photo_urls || [];
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
      <Panel title="Agenda y mensajes">
        <div className="space-y-3">
          <div><Label>Días festivos (YYYY-MM-DD separados por coma)</Label>
            <input className="field" value={(s.holidays || []).join(", ")} onChange={(e) => setS("holidays", e.target.value.split(",").map((x) => x.trim()).filter(Boolean))} data-testid="settings-holidays-input" /></div>
          <p className="text-xs text-muted-foreground">Cancelación, anticipo, faltas, horarios, comisiones y recordatorios se configuran en la pestaña Reglas del salón.</p>
          <div><Label>Mensaje para clientes si la cuenta está suspendida</Label>
            <textarea className="field h-20 py-2" value={s.suspension_message || ""} onChange={(e) => setS("suspension_message", e.target.value)} data-testid="settings-suspension-msg" /></div>
        </div>
      </Panel>
      <Panel title="Portal público" testid="settings-portal">
        <div className="space-y-3">
          <div><Label>Descripción del salón</Label><textarea className="field h-20 py-2" value={f.description || ""} onChange={(e) => setF({ ...f, description: e.target.value })} data-testid="settings-description" /></div>
          <div><Label>Logo</Label><FieldInput field={{ key: "logo_url", type: "image" }} value={f.logo_url} onChange={(v) => setF({ ...f, logo_url: v })} /></div>
          {[0, 1, 2].map((i) => <div key={i}><Label>Foto {i + 1}{i === 0 ? " (portada)" : ""}</Label><FieldInput field={{ key: `photo_${i}`, type: "image" }} value={photos[i]} onChange={(v) => { const p = [...photos]; p[i] = v; setF({ ...f, photo_urls: p.filter(Boolean) }); }} /></div>)}
          <div className="grid grid-cols-3 gap-2">{["instagram", "facebook", "tiktok"].map((k) => <div key={k}><Label>{k}</Label><input className="field" placeholder="https://..." value={social[k] || ""} onChange={(e) => setF({ ...f, social: { ...social, [k]: e.target.value } })} data-testid={`settings-${k}`} /></div>)}</div>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.show_team !== false} onChange={(e) => setF({ ...f, show_team: e.target.checked })} data-testid="settings-show-team" />Mostrar sección Equipo</label>
        </div>
      </Panel>
      <Panel title="Plantilla de recordatorio y textos legales" testid="settings-policy">
        <div className="space-y-3">
          <div><Label>Plantilla de recordatorio ({"{nombre} {servicio} {fecha} {hora} {estilista} {sucursal} {direccion} {enlace} {horas_cancelar} {horas_reprogramar}"})</Label><textarea className="field h-20 py-2" value={s.reminder_template || ""} placeholder="Vacío = mensaje predeterminado" onChange={(e) => setS("reminder_template", e.target.value)} data-testid="settings-reminder-template" /></div>
          <div><Label>Términos y condiciones</Label><textarea className="field h-16 py-2" value={legal.terms || ""} placeholder="Vacío = texto predeterminado" onChange={(e) => setS("legal", { ...legal, terms: e.target.value })} data-testid="settings-terms" /></div>
          <div><Label>Política de privacidad</Label><textarea className="field h-16 py-2" value={legal.privacy || ""} placeholder="Vacío = texto predeterminado" onChange={(e) => setS("legal", { ...legal, privacy: e.target.value })} data-testid="settings-privacy" /></div>
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
  const [params, setParams] = useSearchParams();
  const { user } = useAuth();
  const admin = ["company_admin", "super_admin"].includes(user?.role);
  return (
    <div data-testid="settings-page">
      <PageHeader title="Configuración" subtitle="Empresa, usuarios y trazabilidad" />
      <Tabs value={params.get("tab") || "general"} onValueChange={(v) => setParams({ tab: v })}>
        <TabsList className="mb-6 flex-wrap"><TabsTrigger value="general" data-testid="tab-general">General</TabsTrigger><TabsTrigger value="reglas" data-testid="tab-rules">Reglas del salón</TabsTrigger>{admin && <><TabsTrigger value="users" data-testid="tab-users">Usuarios y roles</TabsTrigger><TabsTrigger value="audit" data-testid="tab-audit">Auditoría</TabsTrigger></>}</TabsList>
        <TabsContent value="general"><General /></TabsContent>
        <TabsContent value="reglas"><SalonRules /></TabsContent>
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
