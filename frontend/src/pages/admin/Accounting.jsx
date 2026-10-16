import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Download, FileText, Plus } from "lucide-react";
import { api, errMsg, money, todayStr, download } from "@/lib/api";
import { Label } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";

export const METHODS = { transfer: "Transferencia", deposit: "Depósito bancario", cash: "Efectivo", check: "Cheque", card: "Tarjeta", other: "Otro" };

export function ManualPaymentDialog({ open, onClose, companyId, onDone }) {
  const [companies, setCompanies] = useState([]);
  const [pending, setPending] = useState([]);
  const [f, setF] = useState({});
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!open) return;
    setF({ company_id: companyId || "", method: "transfer", date: todayStr(), amount: "", reference: "", invoice_id: "", note: "" });
    if (!companyId) api.get("/admin/companies").then((r) => setCompanies(r.data)).catch(() => {});
  }, [open, companyId]);
  useEffect(() => {
    if (!open || !f.company_id) { setPending([]); return; }
    api.get(`/admin/companies/${f.company_id}/account-statement`).then((r) => setPending(r.data.pending_invoices)).catch(() => setPending([]));
  }, [open, f.company_id]);
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const pickInvoice = (id) => { const inv = pending.find((i) => i.id === id); setF((x) => ({ ...x, invoice_id: id, amount: inv ? inv.total : x.amount })); };
  const save = async () => {
    setBusy(true);
    try { await api.post("/admin/payments/manual", f); toast.success("Pago registrado"); onDone?.(); onClose(); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md" data-testid="manual-payment-dialog">
        <DialogHeader><DialogTitle>Registrar pago manual</DialogTitle><DialogDescription>Para pagos recibidos fuera de la plataforma: transferencia, depósito, efectivo o cheque.</DialogDescription></DialogHeader>
        <div className="space-y-3 text-sm">
          {!companyId && <div><Label>Empresa</Label><select className="field" value={f.company_id || ""} onChange={(e) => setF({ ...f, company_id: e.target.value, invoice_id: "" })} data-testid="mp-company-select"><option value="">— Seleccione —</option>{companies.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>}
          <div><Label>Aplicar a factura</Label><select className="field" value={f.invoice_id || ""} onChange={(e) => pickInvoice(e.target.value)} data-testid="mp-invoice-select"><option value="">Abono a cuenta (sin factura)</option>{pending.map((i) => <option key={i.id} value={i.id}>{i.number} · {i.date} · {money(i.total)}</option>)}</select></div>
          <div className="grid grid-cols-2 gap-3">
            <div><Label>Monto</Label><input type="number" step="0.01" min="0" className="field" value={f.amount ?? ""} onChange={(e) => set("amount", e.target.value)} data-testid="mp-amount-input" /></div>
            <div><Label>Fecha del pago</Label><input type="date" className="field" max={todayStr()} value={f.date || ""} onChange={(e) => set("date", e.target.value)} data-testid="mp-date-input" /></div>
            <div><Label>Método</Label><select className="field" value={f.method} onChange={(e) => set("method", e.target.value)} data-testid="mp-method-select">{Object.entries(METHODS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
            <div><Label>Referencia / boleta</Label><input className="field" value={f.reference || ""} onChange={(e) => set("reference", e.target.value)} data-testid="mp-reference-input" /></div>
          </div>
          <div><Label>Nota (opcional)</Label><input className="field" value={f.note || ""} onChange={(e) => set("note", e.target.value)} data-testid="mp-note-input" /></div>
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} data-testid="mp-cancel">Cancelar</Button>
          <Button onClick={save} disabled={busy || !f.company_id || !(Number(f.amount) > 0)} data-testid="mp-save">{busy ? "Guardando..." : "Registrar pago"}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function AccountStatement({ base, cur, slug, reloadKey }) {
  const [start, setStart] = useState(todayStr().slice(0, 5) + "01-01");
  const [end, setEnd] = useState(todayStr());
  const [d, setD] = useState(null);
  useEffect(() => { api.get(base, { params: { start, end } }).then((r) => setD(r.data)).catch((e) => toast.error(errMsg(e))); }, [base, start, end, reloadKey]);
  const file = (fmt) => download(`${base}?start=${start}&end=${end}&format=${fmt}`, `estado_cuenta_${slug}_${start}_${end}.${fmt}`).catch((e) => toast.error(errMsg(e)));
  return (
    <div data-testid="account-statement">
      <div className="mb-3 flex flex-wrap items-end gap-2">
        <div><Label>Desde</Label><input type="date" className="field" value={start} onChange={(e) => setStart(e.target.value)} data-testid="as-start" /></div>
        <div><Label>Hasta</Label><input type="date" className="field" value={end} onChange={(e) => setEnd(e.target.value)} data-testid="as-end" /></div>
        <Button variant="outline" size="sm" onClick={() => file("pdf")} data-testid="as-pdf"><FileText className="mr-1 h-4 w-4" />PDF</Button>
        <Button variant="outline" size="sm" onClick={() => file("xlsx")} data-testid="as-xlsx"><Download className="mr-1 h-4 w-4" />Excel</Button>
      </div>
      {d && <>
        <div className="mb-2 grid grid-cols-4 gap-2 rounded-xl bg-secondary/60 p-3 text-xs">
          <div>Saldo anterior<br /><b data-testid="as-opening">{money(d.opening, cur)}</b></div>
          <div>Cargos<br /><b>{money(d.charges, cur)}</b></div>
          <div>Abonos<br /><b>{money(d.payments, cur)}</b></div>
          <div>Saldo al cierre<br /><b data-testid="as-closing" className={d.closing > 0 ? "text-rose-700" : "text-emerald-700"}>{money(d.closing, cur)}</b></div>
        </div>
        <div className="max-h-72 overflow-auto rounded-xl border">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-secondary text-left uppercase text-slate-500"><tr>{["Fecha", "Documento", "Concepto", "Cargo", "Abono", "Saldo"].map((h) => <th key={h} className="px-2 py-2">{h}</th>)}</tr></thead>
            <tbody>
              {d.rows.map((r, i) => (
                <tr key={i} className="border-t" data-testid={`as-row-${i}`}>
                  <td className="px-2 py-1.5">{r.date}</td><td className="px-2 py-1.5 font-mono">{r.doc}</td><td className="px-2 py-1.5">{r.desc}</td>
                  <td className="px-2 py-1.5 text-right">{r.charge ? money(r.charge, cur) : ""}</td><td className="px-2 py-1.5 text-right text-emerald-700">{r.payment ? money(r.payment, cur) : ""}</td>
                  <td className="px-2 py-1.5 text-right font-semibold">{money(r.balance, cur)}</td>
                </tr>
              ))}
              {!d.rows.length && <tr><td colSpan={6} className="px-2 py-6 text-center text-muted-foreground" data-testid="as-empty">Sin movimientos en este periodo.</td></tr>}
            </tbody>
          </table>
        </div>
      </>}
    </div>
  );
}

export function PaymentButton({ companyId, onDone }) {
  const [open, setOpen] = useState(false);
  return (<>
    <Button size="sm" onClick={() => setOpen(true)} data-testid="register-payment-btn"><Plus className="mr-1 h-4 w-4" />Registrar pago</Button>
    <ManualPaymentDialog open={open} onClose={() => setOpen(false)} companyId={companyId} onDone={onDone} />
  </>);
}
