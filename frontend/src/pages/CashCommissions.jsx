import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Download, Ban } from "lucide-react";
import { api, errMsg, money, todayStr, download, addDays } from "@/lib/api";
import { useAuth } from "@/context/Auth";
import { PageHeader, Panel, Kpi, Label, Loader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { METHODS } from "@/components/Checkout";

export function CashClose() {
  const { user } = useAuth();
  const [date, setDate] = useState(todayStr());
  const [d, setD] = useState(null);
  const load = () => api.get("/cash", { params: { date } }).then((r) => setD(r.data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, [date]); // eslint-disable-line
  const voidSale = async (s) => {
    const reason = window.prompt("Motivo de la anulación");
    if (!reason) return;
    try { await api.post(`/sales/${s.id}/void`, { reason }); toast.success("Cobro anulado"); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div data-testid="cash-page">
      <PageHeader title="Cierre de caja" subtitle="Cobros registrados manualmente (sin pasarela)"
        action={<><input type="date" className="field w-44" value={date} onChange={(e) => setDate(e.target.value)} data-testid="cash-date" />
          <Button variant="outline" onClick={() => download(`/cash?date=${date}&format=xlsx`, `cierre_${date}.xlsx`)} data-testid="cash-export"><Download className="mr-1 h-4 w-4" />Exportar</Button></>} />
      {!d ? <Loader /> : <>
        <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
          <Kpi label="Total cobrado" value={money(d.total)} testid="cash-total" />
          <Kpi label="Propinas" value={money(d.tips)} testid="cash-tips" />
          <Kpi label="Descuentos" value={money(d.discounts)} testid="cash-discounts" />
          <Kpi label="Cobros" value={d.count} testid="cash-count" />
        </div>
        <div className="mb-6 grid gap-6 lg:grid-cols-3">
          <Panel title="Por método" testid="cash-by-method"><ul className="space-y-1 text-sm">{Object.entries(d.by_method).map(([k, v]) => <li key={k} className="flex justify-between"><span>{METHODS[k]}</span><b>{money(v)}</b></li>)}</ul></Panel>
          <Panel title="Por sucursal"><ul className="space-y-1 text-sm">{Object.entries(d.by_branch).map(([k, v]) => <li key={k} className="flex justify-between"><span>{k}</span><b>{money(v)}</b></li>)}</ul></Panel>
          <Panel title="Por estilista"><ul className="space-y-1 text-sm">{d.by_stylist.map((x) => <li key={x.name} className="flex justify-between"><span>{x.name}</span><span>{money(x.sales)} · propina {money(x.tips)}</span></li>)}</ul></Panel>
        </div>
        <Panel title="Detalle">
          <table className="w-full text-sm" data-testid="cash-table">
            <thead className="text-left text-xs uppercase text-slate-500"><tr><th className="py-2">Hora</th><th>Concepto</th><th>Estilista</th><th>Pagos</th><th>Total</th><th /></tr></thead>
            <tbody>{d.sales.map((s) => (
              <tr key={s.id} className={`border-t ${s.voided ? "text-muted-foreground line-through" : ""}`}>
                <td className="py-2">{s.local_time}</td><td>{s.description}</td><td>{s.stylist_name}</td>
                <td className="text-xs">{s.payments.map((p) => `${METHODS[p.method]} ${money(p.amount)}`).join(" + ")}</td><td>{money(s.total)}</td>
                <td>{!s.voided && user.role === "company_admin" && <Button size="sm" variant="ghost" onClick={() => voidSale(s)} data-testid={`void-${s.id}`}><Ban className="h-4 w-4 text-rose-600" /></Button>}</td>
              </tr>
            ))}</tbody>
          </table>
        </Panel>
      </>}
    </div>
  );
}

export function Commissions() {
  const [start, setStart] = useState(todayStr().slice(0, 8) + "01");
  const [end, setEnd] = useState(todayStr());
  const [rows, setRows] = useState(null);
  const [period, setPeriod] = useState("");
  useEffect(() => {
    api.get("/salon-rules").then((r) => {
      const p = r.data.effective.pay_period, d = todayStr();
      setPeriod(r.data.schema.find((x) => x.key === "pay_period").options[p]);
      setStart(p === "weekly" ? addDays(d, -6) : p === "biweekly" ? (d.slice(8) > "15" ? d.slice(0, 8) + "16" : d.slice(0, 8) + "01") : d.slice(0, 8) + "01");
    }).catch(() => {});
  }, []);
  useEffect(() => { api.get("/commissions", { params: { start, end } }).then((r) => setRows(r.data)).catch((e) => toast.error(errMsg(e))); }, [start, end]);
  return (
    <div data-testid="commissions-page">
      <PageHeader title="Comisiones" subtitle="Calculadas al registrar cada cobro; los cambios de porcentaje no alteran cobros anteriores"
        action={<Button variant="outline" onClick={() => download(`/commissions?start=${start}&end=${end}&format=xlsx`, `comisiones_${start}_${end}.xlsx`)} data-testid="commissions-export"><Download className="mr-1 h-4 w-4" />Excel</Button>} />
      <div className="mb-5 flex flex-wrap items-end gap-3">
        {period && <span className="rounded-full bg-secondary px-3 py-1.5 text-xs font-medium" data-testid="comm-period">Periodo de pago: {period}</span>}
        <div><Label>Desde</Label><input type="date" className="field" value={start} onChange={(e) => setStart(e.target.value)} data-testid="comm-start" /></div>
        <div><Label>Hasta</Label><input type="date" className="field" value={end} onChange={(e) => setEnd(e.target.value)} data-testid="comm-end" /></div>
        <Button variant="ghost" onClick={() => { const d = todayStr(); setStart(d.slice(8) > "15" ? d.slice(0, 8) + "16" : d.slice(0, 8) + "01"); setEnd(d); }}>Quincena actual</Button>
        <Button variant="ghost" onClick={() => { setStart(addDays(todayStr(), -30)); setEnd(todayStr()); }}>Últimos 30 días</Button>
      </div>
      {!rows ? <Loader /> : (
        <div className="overflow-x-auto rounded-2xl border bg-white">
          <table className="w-full text-sm" data-testid="commissions-table">
            <thead className="bg-secondary/60 text-left text-xs uppercase text-slate-500"><tr>{["Estilista", "Servicios", "Ventas", "Propinas", "Comisión", "Sueldo base", "Total a pagar"].map((h) => <th key={h} className="px-4 py-3">{h}</th>)}</tr></thead>
            <tbody>{rows.map((x) => <tr key={x.stylist} className="border-t"><td className="px-4 py-3 font-medium">{x.stylist}</td><td className="px-4 py-3">{x.services}</td><td className="px-4 py-3">{money(x.sales)}</td><td className="px-4 py-3">{money(x.tips)}</td><td className="px-4 py-3">{money(x.commission)}</td><td className="px-4 py-3">{money(x.base_salary)}</td><td className="px-4 py-3 font-semibold">{money(x.total_pay)}</td></tr>)}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}
