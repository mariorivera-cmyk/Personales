import { useEffect, useState } from "react";
import { toast } from "sonner";
import { TrendingUp, Building2, Repeat, Percent, FileSpreadsheet } from "lucide-react";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, PieChart, Pie, Cell, Legend } from "recharts";
import { api, errMsg, money, download, CO_STATUS } from "@/lib/api";
import { PageHeader, Kpi, Panel } from "@/components/Common";
import { Button } from "@/components/ui/button";

const C = ["#C2410C", "#059669", "#D97706", "#E11D48", "#0369A1", "#475569"];

export default function AdminDashboard() {
  const [m, setM] = useState(null);
  const load = () => api.get("/admin/metrics").then((r) => setM(r.data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, []);
  if (!m) return null;
  const cur = m.currency;
  return (
    <div data-testid="admin-dashboard-page">
      <PageHeader title="Panel SaaS" subtitle="Indicadores del negocio de la plataforma"
        action={<Button variant="outline" onClick={() => download("/admin/export", "estado_cuenta_consolidado.xlsx")} data-testid="export-xlsx-btn"><FileSpreadsheet className="mr-1 h-4 w-4" />Exportar Excel</Button>} />
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi label="MRR" value={money(m.mrr, cur)} icon={TrendingUp} testid="kpi-mrr" />
        <Kpi label="ARR" value={money(m.arr, cur)} icon={TrendingUp} testid="kpi-arr" />
        <Kpi label="Churn (30 días)" value={`${m.churn}%`} icon={Repeat} testid="kpi-churn" accent="text-rose-600" />
        <Kpi label="Conversión prueba → pago" value={`${m.trial_conversion}%`} icon={Percent} testid="kpi-trial-conv" accent="text-emerald-600" />
      </div>
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {Object.entries(m.counts).map(([k, v]) => (
          <div key={k} className="rounded-xl border bg-white p-3" data-testid={`count-${k}`}><div className="text-xs text-muted-foreground">{CO_STATUS[k]}</div><div className="flex items-center gap-1 text-2xl font-bold"><Building2 className="h-4 w-4 text-slate-400" />{v}</div></div>
        ))}
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <Panel title="Ingresos por mes" className="lg:col-span-2">
          <div className="h-64"><ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 1, height: 1 }}><BarChart data={m.by_month}><CartesianGrid strokeDasharray="3 3" stroke="#eee" /><XAxis dataKey="month" fontSize={11} /><YAxis fontSize={11} /><Tooltip /><Bar dataKey="value" name="Ingresos" fill="#C2410C" radius={[6, 6, 0, 0]} /></BarChart></ResponsiveContainer></div>
        </Panel>
        <Panel title="Ingresos por plan">
          <div className="h-64"><ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 1, height: 1 }}><PieChart><Pie data={m.by_plan} dataKey="value" nameKey="name" innerRadius={50} outerRadius={80}>{m.by_plan.map((_, i) => <Cell key={i} fill={C[i % C.length]} />)}</Pie><Tooltip /><Legend /></PieChart></ResponsiveContainer></div>
        </Panel>
        <Panel title="Ingresos por módulo">
          {m.by_module.length === 0 ? <p className="text-sm text-muted-foreground">Sin ingresos por módulos adicionales aún.</p> :
            <ul className="space-y-1 text-sm">{m.by_module.map((x) => <li key={x.name} className="flex justify-between"><span>{x.name}</span><b>{money(x.value, cur)}</b></li>)}</ul>}
        </Panel>
        <Panel title="WhatsApp: costo vs facturado (mes)" className="lg:col-span-2">
          <table className="w-full text-sm" data-testid="wa-cost-table">
            <thead className="text-left text-xs uppercase text-slate-500"><tr><th className="py-2">Empresa</th><th>Mensajes</th><th>Costo</th><th>Facturado</th></tr></thead>
            <tbody>{m.whatsapp.map((w) => <tr key={w.company} className="border-t"><td className="py-2">{w.company}</td><td>{w.messages}</td><td>{money(w.cost, cur)}</td><td>{money(w.billed, cur)}</td></tr>)}</tbody>
          </table>
        </Panel>
      </div>
    </div>
  );
}
