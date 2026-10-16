import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg, money } from "@/lib/api";
import { PageHeader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { METHODS, PaymentButton } from "@/pages/admin/Accounting";

const ST = { approved: "Aprobado", rejected: "Rechazado", pending: "Pendiente", void: "Anulado" };

function VoidDialog({ p, onClose, onDone }) {
  const [reason, setReason] = useState("");
  const go = async () => {
    try { await api.post(`/admin/payments/${p.id}/void`, { reason }); toast.success("Pago anulado"); onDone(); onClose(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-sm" data-testid="void-payment-dialog">
        <DialogHeader><DialogTitle>Anular pago de {money(p.amount, p.currency)}</DialogTitle></DialogHeader>
        <p className="text-sm text-muted-foreground">Si estaba aplicado a una factura, la factura vuelve a quedar pendiente.</p>
        <input className="field" placeholder="Motivo de la anulación" value={reason} onChange={(e) => setReason(e.target.value)} data-testid="void-reason-input" />
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} data-testid="void-cancel">Cancelar</Button>
          <Button variant="destructive" disabled={!reason.trim()} onClick={go} data-testid="void-confirm">Anular pago</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function AdminPayments() {
  const [rows, setRows] = useState([]);
  const [voiding, setVoiding] = useState(null);
  const load = () => api.get("/admin/payments").then((r) => setRows(r.data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, []);
  const decide = async (p, approve) => {
    try { await api.post(`/admin/payments/${p.id}/decision`, { approve }); toast.success(approve ? "Pago aprobado y empresa reactivada" : "Pago rechazado"); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div data-testid="admin-payments-page">
      <PageHeader title="Pagos" subtitle="Pagos con tarjeta, transferencias por aprobar y pagos registrados a mano" action={<PaymentButton onDone={load} />} />
      <p className="-mt-4 mb-4 text-sm text-muted-foreground" data-testid="payments-help">Los pagos recibidos fuera de la plataforma (transferencia, depósito, efectivo o cheque) se registran con <b>Registrar pago</b>; si se aplican a una factura, esta queda pagada y la empresa se reactiva.</p>
      <div className="overflow-x-auto rounded-2xl border bg-white">
        <table className="w-full text-sm" data-testid="payments-table">
          <thead className="bg-secondary/60 text-left text-xs uppercase tracking-wider text-slate-500">
            <tr>{["Fecha", "Empresa", "Factura", "Método", "Referencia", "Monto", "Estado", ""].map((h) => <th key={h} className="px-4 py-3">{h}</th>)}</tr>
          </thead>
          <tbody>{rows.map((p) => (
            <tr key={p.id} className="border-t" data-testid={`payment-row-${p.id}`}>
              <td className="px-4 py-3">{p.date}</td><td className="px-4 py-3">{p.company_name}</td><td className="px-4 py-3 font-mono text-xs">{p.invoice_number || "A cuenta"}</td>
              <td className="px-4 py-3">{METHODS[p.method] || p.method}{p.manual && <span className="ml-1 rounded bg-secondary px-1.5 py-0.5 text-[10px] uppercase">manual</span>}</td>
              <td className="px-4 py-3 text-xs">{p.reference}{p.note && <span className="block text-muted-foreground">{p.note}</span>}</td>
              <td className="px-4 py-3">{money(p.amount, p.currency)}</td>
              <td className="px-4 py-3">{ST[p.status]}{p.void_reason && <span className="block text-xs text-muted-foreground">{p.void_reason}</span>}</td>
              <td className="whitespace-nowrap px-4 py-3 text-right">{p.status === "pending" && <>
                <Button size="sm" onClick={() => decide(p, true)} data-testid={`payment-approve-${p.id}`}>Aprobar</Button>
                <Button size="sm" variant="ghost" onClick={() => decide(p, false)} data-testid={`payment-reject-${p.id}`}>Rechazar</Button></>}
                {p.manual && p.status === "approved" && <Button size="sm" variant="ghost" className="text-rose-600" onClick={() => setVoiding(p)} data-testid={`payment-void-${p.id}`}>Anular</Button>}</td>
            </tr>
          ))}
          {!rows.length && <tr><td colSpan={8} className="px-4 py-8 text-center text-muted-foreground">Aún no hay pagos.</td></tr>}</tbody>
        </table>
      </div>
      {voiding && <VoidDialog p={voiding} onClose={() => setVoiding(null)} onDone={load} />}
    </div>
  );
}
