import { useState } from "react";
import { toast } from "sonner";
import { Zap } from "lucide-react";
import { api, errMsg, money } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";

export function AdvanceChargeButton({ company, onDone }) {
  const [pv, setPv] = useState(null);
  const [ok, setOk] = useState(false);
  const [busy, setBusy] = useState(false);
  const open = () => api.get(`/admin/companies/${company.id}/advance-charge`).then((r) => { setPv(r.data); setOk(false); }).catch((e) => toast.error(errMsg(e)));
  const go = async () => {
    setBusy(true);
    try { const r = await api.post(`/admin/companies/${company.id}/advance-charge`, { confirm: true }); toast.success(`Cobro aprobado: factura ${r.data.invoice}. Próximo cobro: ${r.data.next_billing_date}`); setPv(null); onDone(); }
    catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const allowed = ["active", "trial"].includes(company.status);
  return (<>
    <Button variant="outline" size="sm" onClick={open} disabled={!allowed} title={allowed ? "" : "Solo empresas activas o en prueba"} data-testid="advance-charge-btn"><Zap className="mr-1 h-4 w-4" />Cobro adelantado</Button>
    <Dialog open={!!pv} onOpenChange={(o) => !o && setPv(null)}>
      {pv && <DialogContent className="max-w-md" data-testid="advance-charge-dialog">
        <DialogHeader><DialogTitle>Cobro adelantado a «{company.name}»</DialogTitle>
          <DialogDescription>Se cobrará ahora a la tarjeta {pv.card_last4 ? `terminada en ${pv.card_last4}` : "(no registrada)"} el periodo {pv.cycle === "annual" ? "anual" : "mensual"} siguiente.</DialogDescription></DialogHeader>
        <div className="space-y-1 rounded-xl bg-secondary/60 p-3 text-sm">
          <div data-testid="advance-period">Periodo: <b>{pv.period_from}</b> a <b>{pv.period_to}</b></div>
          {pv.items.map((i) => <div key={i.desc} className="flex justify-between text-xs"><span>{i.desc}</span><span>{money(i.amount, pv.currency)}</span></div>)}
          <div className="flex justify-between text-xs"><span>IVA</span><span>{money(pv.tax, pv.currency)}</span></div>
          <div className="flex justify-between border-t pt-1 font-semibold"><span>Total</span><span data-testid="advance-total">{money(pv.total, pv.currency)}</span></div>
          <div className="text-xs text-muted-foreground">El próximo cobro automático pasará al {pv.period_to}.</div>
        </div>
        {!pv.card_last4 && <p className="text-sm font-medium text-rose-700" data-testid="advance-no-card">La empresa no tiene tarjeta registrada. Use «Registrar pago» si pagó por otro medio.</p>}
        <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-0.5 h-4 w-4" checked={ok} onChange={(e) => setOk(e.target.checked)} data-testid="advance-confirm-check" />Confirmo que deseo realizar este cobro ahora.</label>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => setPv(null)} data-testid="advance-cancel">Cancelar</Button>
          <Button onClick={go} disabled={!ok || busy || !pv.card_last4} data-testid="advance-confirm">{busy ? "Cobrando..." : `Cobrar ${money(pv.total, pv.currency)}`}</Button>
        </div>
      </DialogContent>}
    </Dialog>
  </>);
}
