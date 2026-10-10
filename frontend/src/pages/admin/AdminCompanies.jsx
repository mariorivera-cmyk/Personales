import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Plus, LogIn, Eye } from "lucide-react";
import { api, errMsg, money, CO_STATUS } from "@/lib/api";
import { useAuth } from "@/context/Auth";
import { PageHeader, CompanyBadge, Label } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { FormDialog } from "@/components/CrudPage";
import { InvoiceTable } from "@/pages/Billing";

function Detail({ id, plans, modules, onClose, reload }) {
  const [d, setD] = useState(null);
  const [f, setF] = useState({});
  const load = useCallback(() => api.get(`/admin/companies/${id}/statement`).then((r) => { setD(r.data); setF(r.data.company); }), [id]);
  useEffect(() => { load(); }, [load]);
  if (!d) return null;
  const act = async (fn, msg) => { try { await fn(); toast.success(msg); load(); reload(); } catch (e) { toast.error(errMsg(e)); } };
  const cur = d.company.currency;
  return (
    <div className="space-y-6 text-sm" data-testid="company-detail">
      <div className="grid grid-cols-2 gap-3">
        <div><Label>Estado</Label><select className="field" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })} data-testid="company-status-select">{Object.entries(CO_STATUS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
        <div><Label>Plan</Label><select className="field" value={f.plan_id} onChange={(e) => setF({ ...f, plan_id: e.target.value })} data-testid="company-plan-select">{plans.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></div>
        <div><Label>Ciclo</Label><select className="field" value={f.billing_cycle} onChange={(e) => setF({ ...f, billing_cycle: e.target.value })}><option value="monthly">Mensual</option><option value="annual">Anual</option></select></div>
        <div><Label>Precio preferencial (% desc.)</Label><input type="number" className="field" value={f.coupon_pct || 0} onChange={(e) => setF({ ...f, coupon_pct: Number(e.target.value) })} data-testid="company-discount-input" /></div>
        <div><Label>Próximo cobro</Label><input type="date" className="field" value={f.next_billing_date || ""} onChange={(e) => setF({ ...f, next_billing_date: e.target.value })} /></div>
        <div><Label>Fin de prueba</Label><input type="date" className="field" value={f.trial_ends || ""} onChange={(e) => setF({ ...f, trial_ends: e.target.value })} /></div>
      </div>
      <Button onClick={() => act(() => api.put(`/admin/companies/${id}`, f), "Empresa actualizada")} data-testid="company-save-btn">Guardar cambios</Button>
      <div>
        <h4 className="mb-2 font-semibold">Módulos (efecto inmediato)</h4>
        <div className="grid grid-cols-2 gap-2">
          {modules.map((m) => (
            <label key={m.key} className="flex items-center justify-between rounded-lg border p-2">
              <span>{m.name}<span className="block text-xs text-muted-foreground">{money(m.price_monthly, cur)}/mes</span></span>
              <Switch checked={d.company.enabled_modules.includes(m.key)} onCheckedChange={(v) => act(() => api.post(`/admin/companies/${id}/modules`, { key: m.key, enabled: v }), "Módulo actualizado")} data-testid={`admin-module-${m.key}`} />
            </label>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-3 gap-2 rounded-xl bg-secondary/60 p-3">
        <div>Cargos<br /><b>{money(d.charged, cur)}</b></div><div>Pagos<br /><b>{money(d.paid, cur)}</b></div><div>Saldo<br /><b data-testid="company-balance">{money(d.balance, cur)}</b></div>
        <div className="col-span-3 text-xs">Costo mensual: {money(d.monthly_total, cur)} · Ciclo: {money(d.cycle_total, cur)} · WhatsApp: {d.whatsapp.used} msgs</div>
      </div>
      <div><h4 className="mb-2 font-semibold">Facturas</h4><InvoiceTable invoices={d.invoices} cur={cur} /></div>
      <div><h4 className="mb-2 font-semibold">Historial de plan y módulos</h4>
        <ul className="space-y-1">{d.history.map((h) => <li key={h.id} className="text-xs"><span className="text-muted-foreground">{h.created_at.slice(0, 16).replace("T", " ")} · {h.user_email}</span> — {h.change}</li>)}</ul></div>
    </div>
  );
}

export default function AdminCompanies() {
  const { enterCompany } = useAuth();
  const nav = useNavigate();
  const [rows, setRows] = useState([]);
  const [plans, setPlans] = useState([]);
  const [modules, setModules] = useState([]);
  const [sel, setSel] = useState(null);
  const [creating, setCreating] = useState(false);
  const load = () => api.get("/admin/companies").then((r) => setRows(r.data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); api.get("/admin/plans").then((r) => setPlans(r.data)); api.get("/admin/modules").then((r) => setModules(r.data)); }, []);
  const enter = async (c) => { await enterCompany(c.id); nav("/app"); };
  return (
    <div data-testid="admin-companies-page">
      <PageHeader title="Empresas" subtitle="Clientes de la plataforma, estado de cuenta y módulos"
        action={<Button onClick={() => setCreating(true)} data-testid="new-company-btn"><Plus className="mr-1 h-4 w-4" />Nueva empresa</Button>} />
      <div className="overflow-x-auto rounded-2xl border bg-white">
        <table className="w-full text-sm" data-testid="companies-table">
          <thead className="bg-secondary/60 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr>{["Empresa", "NIT", "Plan", "Estado", "MRR", "Saldo", "Próximo cobro", ""].map((h) => <th key={h} className="px-4 py-3">{h}</th>)}</tr>
          </thead>
          <tbody>{rows.map((c) => (
            <tr key={c.id} className="border-t hover:bg-secondary/30" data-testid={`company-row-${c.slug}`}>
              <td className="px-4 py-3"><div className="font-medium">{c.name}</div><div className="text-xs text-muted-foreground">{c.whatsapp_number} · /b/{c.slug}</div></td>
              <td className="px-4 py-3">{c.nit}</td><td className="px-4 py-3">{c.plan_name}</td><td className="px-4 py-3"><CompanyBadge status={c.status} /></td>
              <td className="px-4 py-3">{money(c.mrr, c.currency)}</td><td className="px-4 py-3">{money(c.balance, c.currency)}</td>
              <td className="px-4 py-3">{c.next_billing_date || c.trial_ends || "—"}</td>
              <td className="whitespace-nowrap px-4 py-3 text-right">
                <Button size="sm" variant="ghost" onClick={() => setSel(c.id)} data-testid={`company-view-${c.slug}`}><Eye className="h-4 w-4" /></Button>
                <Button size="sm" variant="outline" onClick={() => enter(c)} data-testid={`company-enter-${c.slug}`}><LogIn className="mr-1 h-4 w-4" />Entrar</Button>
              </td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <Sheet open={!!sel} onOpenChange={(o) => !o && setSel(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-2xl">
          <SheetHeader><SheetTitle>{rows.find((r) => r.id === sel)?.name}</SheetTitle></SheetHeader>
          {sel && <div className="mt-4"><Detail id={sel} plans={plans} modules={modules} onClose={() => setSel(null)} reload={load} /></div>}
        </SheetContent>
      </Sheet>
      <FormDialog open={creating} onOpenChange={setCreating} title="Alta de empresa" testid="company-form" initial={{ billing_cycle: "monthly", status: "trial" }}
        fields={[
          { key: "company_name", label: "Nombre comercial" }, { key: "nit", label: "NIT" }, { key: "slug", label: "Enlace (slug)" },
          { key: "whatsapp_number", label: "Número WhatsApp" }, { key: "contact_name", label: "Contacto" }, { key: "email", label: "Correo administrador", type: "email" },
          { key: "password", label: "Contraseña inicial", type: "password" },
          { key: "plan_id", label: "Plan", type: "select", options: plans.map((p) => ({ value: p.id, label: p.name })) },
          { key: "billing_cycle", label: "Ciclo", type: "select", options: [{ value: "monthly", label: "Mensual" }, { value: "annual", label: "Anual" }] },
          { key: "status", label: "Estado inicial", type: "select", options: [{ value: "trial", label: "Prueba" }, { value: "active", label: "Activa" }] },
        ]}
        onSubmit={async (f) => { await api.post("/admin/companies", f); toast.success("Empresa creada"); load(); }} />
    </div>
  );
}
