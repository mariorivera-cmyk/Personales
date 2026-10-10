import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg, money } from "@/lib/api";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";

const ST = { approved: "Aprobado", rejected: "Rechazado", pending: "Pendiente" };

export default function AdminPayments() {
  const [rows, setRows] = useState([]);
  const load = () => api.get("/admin/payments").then((r) => setRows(r.data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, []);
  const decide = async (p, approve) => {
    try { await api.post(`/admin/payments/${p.id}/decision`, { approve }); toast.success(approve ? "Pago aprobado y empresa reactivada" : "Pago rechazado"); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div data-testid="admin-payments-page">
      <PageHeader title="Pagos" subtitle="Cobros con tarjeta y transferencias pendientes de aprobación manual" />
      <div className="overflow-x-auto rounded-2xl border bg-white">
        <table className="w-full text-sm" data-testid="payments-table">
          <thead className="bg-secondary/60 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr>{["Fecha", "Empresa", "Factura", "Método", "Referencia", "Monto", "Estado", ""].map((h) => <th key={h} className="px-4 py-3">{h}</th>)}</tr>
          </thead>
          <tbody>{rows.map((p) => (
            <tr key={p.id} className="border-t" data-testid={`payment-row-${p.id}`}>
              <td className="px-4 py-3">{p.date}</td><td className="px-4 py-3">{p.company_name}</td><td className="px-4 py-3 font-mono text-xs">{p.invoice_number}</td>
              <td className="px-4 py-3">{p.method === "card" ? "Tarjeta" : "Transferencia"}</td><td className="px-4 py-3 text-xs">{p.reference}</td>
              <td className="px-4 py-3">{money(p.amount, p.currency)}</td><td className="px-4 py-3">{ST[p.status]}</td>
              <td className="whitespace-nowrap px-4 py-3 text-right">{p.status === "pending" && <>
                <Button size="sm" onClick={() => decide(p, true)} data-testid={`payment-approve-${p.id}`}>Aprobar</Button>
                <Button size="sm" variant="ghost" onClick={() => decide(p, false)} data-testid={`payment-reject-${p.id}`}>Rechazar</Button></>}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}
