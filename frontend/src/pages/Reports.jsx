import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";
import { api, errMsg, money, todayStr, addDays } from "@/lib/api";
import { PageHeader, Panel, Label } from "@/components/Common";

const GROUPS = { branch: "Sucursal", stylist: "Estilista", service: "Servicio", client: "Cliente" };

export default function Reports() {
  const [group, setGroup] = useState("branch");
  const [start, setStart] = useState(addDays(todayStr(), -90));
  const [end, setEnd] = useState(todayStr());
  const [rows, setRows] = useState([]);
  useEffect(() => {
    api.get("/reports", { params: { group, start, end } }).then((r) => setRows(r.data)).catch((e) => toast.error(errMsg(e)));
  }, [group, start, end]);
  const tot = rows.reduce((a, r) => ({ sales: a.sales + r.sales, margin: a.margin + r.margin, c: a.c + r.cancelled, n: a.n + r.no_show }), { sales: 0, margin: 0, c: 0, n: 0 });
  return (
    <div data-testid="reports-page">
      <PageHeader title="Reportería" subtitle={`Ventas ${money(tot.sales)} · Margen ${money(tot.margin)} · Cancelaciones ${tot.c} · No shows ${tot.n}`} />
      <div className="mb-5 flex flex-wrap items-end gap-3">
        <div className="flex rounded-full border bg-white p-1 text-sm">
          {Object.entries(GROUPS).map(([k, l]) => (
            <button key={k} onClick={() => setGroup(k)} className={`rounded-full px-4 py-1.5 ${group === k ? "bg-slate-900 text-white" : ""}`} data-testid={`report-group-${k}`}>{l}</button>
          ))}
        </div>
        <div><Label>Desde</Label><input type="date" className="field" value={start} onChange={(e) => setStart(e.target.value)} data-testid="report-start" /></div>
        <div><Label>Hasta</Label><input type="date" className="field" value={end} onChange={(e) => setEnd(e.target.value)} data-testid="report-end" /></div>
      </div>
      <Panel title={`Ventas por ${GROUPS[group].toLowerCase()}`} className="mb-6">
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 1, height: 1 }}>
            <BarChart data={rows.slice(0, 12)}><CartesianGrid strokeDasharray="3 3" stroke="#eee" /><XAxis dataKey="name" fontSize={11} /><YAxis fontSize={11} /><Tooltip />
              <Bar dataKey="sales" name="Ventas" fill="#C2410C" radius={[6, 6, 0, 0]} /><Bar dataKey="margin" name="Margen" fill="#059669" radius={[6, 6, 0, 0]} /></BarChart>
          </ResponsiveContainer>
        </div>
      </Panel>
      <div className="overflow-x-auto rounded-2xl border bg-white">
        <table className="w-full text-sm" data-testid="report-table">
          <thead className="bg-secondary/60 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr>{[GROUPS[group], "Citas", "Completadas", "Ventas", "Rentabilidad", "Horas ocupadas", "Cancelaciones", "No shows", "Efectividad"].map((h) => <th key={h} className="px-4 py-3">{h}</th>)}</tr>
          </thead>
          <tbody>{rows.map((r) => (
            <tr key={r.name} className="border-t"><td className="px-4 py-3 font-medium">{r.name}</td><td className="px-4 py-3">{r.total}</td><td className="px-4 py-3">{r.completed}</td>
              <td className="px-4 py-3">{money(r.sales)}</td><td className="px-4 py-3">{money(r.margin)}</td><td className="px-4 py-3">{r.hours}</td>
              <td className="px-4 py-3">{r.cancelled}</td><td className="px-4 py-3">{r.no_show}</td><td className="px-4 py-3">{r.effectiveness}%</td></tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}
