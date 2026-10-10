import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { Download, CreditCard } from "lucide-react";
import { api, errMsg, money, download, CO_STATUS } from "@/lib/api";
import { useAuth } from "@/context/Auth";
import { PageHeader, Panel, Kpi, CompanyBadge, Label } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { CardForm } from "@/pages/Signup";

export function InvoiceTable({ invoices, onPay, onTransfer, cur }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" data-testid="invoices-table">
        <thead className="text-left text-xs uppercase text-slate-500"><tr><th className="py-2">Factura</th><th>Fecha</th><th>Concepto</th><th>Total</th><th>Estado</th><th /></tr></thead>
        <tbody>{invoices.map((i) => (
          <tr key={i.id} className="border-t" data-testid={`invoice-row-${i.number}`}>
            <td className="py-2 font-mono text-xs">{i.number}</td><td>{i.date}</td><td className="max-w-[220px] truncate">{i.items.map((x) => x.desc).join(", ")}</td>
            <td>{money(i.total, cur)}</td><td><span className={`rounded-full px-2 py-0.5 text-xs ${i.status === "paid" ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}>{{ paid: "Pagada", pending: "Pendiente", failed: "Rechazada" }[i.status]}</span></td>
            <td className="whitespace-nowrap text-right">
              <Button size="sm" variant="ghost" onClick={() => download(`/invoices/${i.id}/pdf`, `${i.number}.pdf`)} data-testid={`invoice-pdf-${i.number}`}><Download className="h-4 w-4" /></Button>
              {i.status !== "paid" && onPay && <Button size="sm" variant="outline" onClick={() => onPay(i)} data-testid={`invoice-pay-${i.number}`}>Pagar</Button>}
              {i.status !== "paid" && onTransfer && <Button size="sm" variant="ghost" onClick={() => onTransfer(i)} data-testid={`invoice-transfer-${i.number}`}>Transferencia</Button>}
            </td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

export default function Billing() {
  const { refresh } = useAuth();
  const [d, setD] = useState(null);
  const [mods, setMods] = useState([]);
  const [plans, setPlans] = useState([]);
  const [card, setCard] = useState({});
  const load = useCallback(() => api.get("/billing/statement").then((r) => setD(r.data)).catch((e) => toast.error(errMsg(e))), []);
  useEffect(() => { load(); api.get("/public/plans").then((r) => { setMods(r.data.modules); setPlans(r.data.plans); }); }, [load]);
  if (!d) return null;
  const cur = d.company.currency;
  const act = async (fn, msg) => { try { await fn(); toast.success(msg); load(); refresh(); } catch (e) { toast.error(errMsg(e)); } };
  const toggle = (k, on) => act(() => api.post("/billing/modules", { key: k, enabled: on }), on ? "Módulo contratado (cargo prorrateado)" : "Módulo deshabilitado");
  const saveCard = () => act(async () => { const t = await api.post("/gateway/tokenize", card); await api.post("/billing/card", t.data); setCard({}); }, "Tarjeta actualizada");
  const pay = (i) => act(async () => { const r = await api.post(`/billing/pay/${i.id}`); if (!r.data.ok) throw new Error("Pago rechazado por la pasarela"); }, "Pago aprobado");
  const transfer = (i) => { const ref = window.prompt("Número de boleta / referencia de transferencia"); if (ref) act(() => api.post("/billing/transfer", { invoice_id: i.id, reference: ref }), "Transferencia registrada, pendiente de aprobación"); };
  const exportData = async () => {
    const r = await api.get("/billing/export");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(r.data, null, 2)], { type: "application/json" }));
    a.download = "exportacion_datos.json";
    a.click();
  };
  const cancel = () => window.confirm("¿Cancelar el servicio? Sus datos se conservarán 90 días para exportación.") && act(() => api.post("/billing/cancel"), "Servicio cancelado");
  return (
    <div data-testid="billing-page">
      <PageHeader title="Mi suscripción" subtitle={<span className="flex items-center gap-2">Estado: <CompanyBadge status={d.company.status} />{d.company.status === "trial" && ` hasta ${d.company.trial_ends}`}</span>}
        action={<><Button variant="outline" onClick={exportData} data-testid="export-data-btn">Exportar mis datos</Button><Button variant="ghost" onClick={cancel} data-testid="cancel-service-btn">Cancelar servicio</Button></>} />
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi label="Plan" value={d.plan.name} hint={d.company.billing_cycle === "annual" ? "Anual" : "Mensual"} testid="billing-plan" />
        <Kpi label="Costo del ciclo" value={money(d.cycle_total, cur)} hint="antes de IVA" testid="billing-cycle-total" />
        <Kpi label="Saldo pendiente" value={money(d.balance, cur)} testid="billing-balance" accent="text-rose-600" />
        <Kpi label="Próximo cobro" value={d.company.next_billing_date || d.company.trial_ends || "—"} testid="billing-next" />
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <Panel title="Módulos" className="lg:col-span-2" testid="billing-modules">
          <div className="grid gap-2 sm:grid-cols-2">
            {mods.map((m) => {
              const incl = d.plan.included_modules?.includes(m.key);
              const on = d.company.enabled_modules.includes(m.key);
              return (
                <div key={m.key} className="flex items-center justify-between rounded-lg border p-3 text-sm">
                  <div><div className="font-medium">{m.name}</div><div className="text-xs text-muted-foreground">{incl ? "Incluido en su plan" : `${money(m.price_monthly, cur)}/mes`}</div></div>
                  <Switch checked={on} disabled={incl} onCheckedChange={(v) => toggle(m.key, v)} data-testid={`billing-module-${m.key}`} />
                </div>
              );
            })}
          </div>
          <div className="mt-4 flex flex-wrap items-end gap-2 border-t pt-4">
            <div><Label>Cambiar plan</Label>
              <select className="field w-56" defaultValue={d.company.plan_id} id="plan-sel" data-testid="billing-plan-select">{plans.map((p) => <option key={p.id} value={p.id}>{p.name} · {money(p.price_monthly, cur)}/mes</option>)}</select></div>
            <select className="field w-36" defaultValue={d.company.billing_cycle} id="cycle-sel" data-testid="billing-cycle-select"><option value="monthly">Mensual</option><option value="annual">Anual</option></select>
            <Button variant="outline" onClick={() => act(() => api.put("/billing/plan", { plan_id: document.getElementById("plan-sel").value, billing_cycle: document.getElementById("cycle-sel").value }), "Plan actualizado")} data-testid="billing-plan-save">Aplicar</Button>
          </div>
        </Panel>
        <Panel title="Tarjeta registrada" testid="billing-card">
          <div className="mb-3 flex items-center gap-2 text-sm"><CreditCard className="h-4 w-4" />{d.company.card ? `${d.company.card.brand} •••• ${d.company.card.last4}` : "Sin tarjeta"}</div>
          <CardForm value={card} onChange={setCard} />
          <Button className="mt-3 w-full" onClick={saveCard} data-testid="save-card-btn">Actualizar tarjeta</Button>
        </Panel>
      </div>
      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Panel title="Facturas (FEL simulada)" className="lg:col-span-2" testid="billing-invoices"><InvoiceTable invoices={d.invoices} onPay={pay} onTransfer={transfer} cur={cur} /></Panel>
        <Panel title="Consumo WhatsApp (mes)" testid="billing-whatsapp">
          <div className="space-y-1 text-sm"><div>Mensajes: <b>{d.whatsapp.used}</b> / {d.whatsapp.included} incluidos</div><div>Excedente: {d.whatsapp.excess} ({money(d.whatsapp.excess_cost, cur)})</div></div>
          <h4 className="mb-2 mt-5 text-sm font-semibold">Detalle mensual</h4>
          <ul className="space-y-1 text-sm">{d.items.map((i) => <li key={i.desc} className="flex justify-between"><span>{i.desc}</span><span>{money(i.amount, cur)}</span></li>)}</ul>
          <h4 className="mb-2 mt-5 text-sm font-semibold">Notificaciones</h4>
          <ul className="max-h-40 space-y-1 overflow-auto text-xs text-muted-foreground">{d.notifications.map((n) => <li key={n.id}><b>{n.title}:</b> {n.text}</li>)}</ul>
        </Panel>
      </div>
      <Panel title="Historial de cambios" className="mt-6">
        <ul className="space-y-1 text-sm">{d.history.map((h) => <li key={h.id}><span className="text-xs text-muted-foreground">{h.created_at.slice(0, 16).replace("T", " ")} · {h.user_email}</span> — {h.change}</li>)}</ul>
      </Panel>
      <p className="mt-4 text-xs text-muted-foreground">Estado {CO_STATUS[d.company.status]}. Pasarela de pago y FEL en modo SIMULADO.</p>
    </div>
  );
}
