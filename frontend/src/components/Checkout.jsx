import { useState, useEffect } from "react";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";
import { api, errMsg, money } from "@/lib/api";
import { Label } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

export const METHODS = { cash: "Efectivo", card: "Tarjeta (POS)", transfer: "Transferencia" };

export function PaymentRows({ rows, setRows, total }) {
  const paid = rows.reduce((a, r) => a + Number(r.amount || 0), 0);
  const set = (i, k, v) => setRows(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  return (
    <div className="space-y-2" data-testid="payment-rows">
      {rows.map((r, i) => (
        <div key={i} className="flex gap-2">
          <select className="field" value={r.method} onChange={(e) => set(i, "method", e.target.value)} data-testid={`pay-method-${i}`}>
            {Object.entries(METHODS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
          <input type="number" step="0.01" className="field w-36" value={r.amount} onChange={(e) => set(i, "amount", e.target.value)} data-testid={`pay-amount-${i}`} />
          {rows.length > 1 && <Button variant="ghost" size="icon" onClick={() => setRows(rows.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4" /></Button>}
        </div>
      ))}
      <button type="button" className="flex items-center gap-1 text-sm text-primary" onClick={() => setRows([...rows, { method: "cash", amount: Math.max(total - paid, 0).toFixed(2) }])} data-testid="pay-add-row">
        <Plus className="h-3.5 w-3.5" />Pago mixto: agregar otro método
      </button>
      <div className={`text-sm ${Math.abs(paid - total) > 0.01 ? "text-rose-600" : "text-emerald-700"}`} data-testid="pay-balance">
        Pagado {money(paid)} de {money(total)}{Math.abs(paid - total) > 0.01 ? " — la suma debe ser igual al total" : " ✓"}
      </div>
    </div>
  );
}

function Promos({ appt, opts, f, setF }) {
  const [code, setCode] = useState("");
  const check = async () => {
    try { const r = await api.post("/coupons/check", { code }); setF({ ...f, coupon_code: r.data.code, coupon_pct: r.data.percent, apply_membership: false }); toast.success(`Cupón ${r.data.code}: ${r.data.percent}%`); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div className="space-y-2 rounded-lg border p-3" data-testid="checkout-promos">
      {opts.packages.map((p) => (
        <label key={p.id} className="flex items-start gap-2"><input type="checkbox" className="mt-1 h-4 w-4" checked={f.package_id === p.id} onChange={(e) => setF({ ...f, package_id: e.target.checked ? p.id : "" })} data-testid={`checkout-use-package-${p.id}`} />
          <span><b>Usar paquete {p.name}</b> — cubre {appt.service_name} ({money(opts.package_cover)}). Quedan {p.remaining} sesión(es), vence {p.expires}.</span></label>
      ))}
      {opts.membership && <label className="flex items-center gap-2"><input type="checkbox" className="h-4 w-4" checked={!!f.apply_membership} onChange={(e) => setF({ ...f, apply_membership: e.target.checked, coupon_code: "", coupon_pct: 0 })} data-testid="checkout-apply-membership" />Membresía {opts.membership.name}: {opts.membership.percent}% de descuento</label>}
      {f.coupon_code ? <div className="flex items-center justify-between text-emerald-700" data-testid="checkout-coupon-applied">Cupón {f.coupon_code} ({f.coupon_pct}%) aplicado<button className="text-xs underline" onClick={() => setF({ ...f, coupon_code: "", coupon_pct: 0 })}>Quitar</button></div> : (
        <div className="flex gap-2"><input className="field" placeholder="Código de cupón" value={code} onChange={(e) => setCode(e.target.value)} data-testid="checkout-coupon-input" /><Button type="button" variant="outline" onClick={check} disabled={!code.trim()} data-testid="checkout-coupon-apply">Aplicar</Button></div>)}
    </div>
  );
}

export function CheckoutDialog({ appt, onClose, onDone }) {
  const [f, setF] = useState({ discount: 0, tip: 0, discount_reason: "" });
  const [rows, setRows] = useState([]);
  const [opts, setOpts] = useState({ packages: [], package_cover: 0, membership: null });
  const cover = f.package_id ? opts.package_cover : 0;
  const pct = f.apply_membership ? opts.membership?.percent || 0 : f.coupon_pct || 0;
  const promo = appt ? Math.round((appt.price - cover) * pct) / 100 : 0;
  const due = appt ? Math.max(0, Math.round((appt.price - Number(f.discount || 0) - cover - promo - Number(appt.deposit_paid || 0) + Number(f.tip || 0)) * 100) / 100) : 0;
  useEffect(() => {
    if (!appt) return;
    setF({ discount: 0, tip: 0, discount_reason: "" });
    api.get(`/appointments/${appt.id}/checkout-options`).then((r) => {
      setOpts(r.data);
      if (r.data.packages[0]) setF((s) => ({ ...s, package_id: r.data.packages[0].id }));
    }).catch(() => {});
  }, [appt]);
  useEffect(() => { if (appt) setRows(due > 0 ? [{ method: "cash", amount: due.toFixed(2) }] : []); }, [appt, due]);
  if (!appt) return null;
  const submit = async () => {
    try {
      const { coupon_pct, ...body } = f;
      await api.post(`/appointments/${appt.id}/checkout`, { ...body, payments: rows });
      toast.success("Cita atendida y cobro registrado");
      onDone();
    } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md" data-testid="checkout-dialog">
        <DialogHeader><DialogTitle className="font-heading">Cobro en caja · {appt.client_name}</DialogTitle></DialogHeader>
        <div className="space-y-3 text-sm">
          <div>{appt.service_name}{appt.addon_names?.length ? ` + ${appt.addon_names.join(", ")}` : ""}: <b>{money(appt.price)}</b>{appt.deposit_paid ? ` · Anticipo recibido ${money(appt.deposit_paid)}` : ""}</div>
          <Promos appt={appt} opts={opts} f={f} setF={setF} />
          <div className="grid grid-cols-2 gap-2">
            <div><Label>Descuento</Label><input type="number" className="field" value={f.discount} onChange={(e) => setF({ ...f, discount: e.target.value })} data-testid="checkout-discount" /></div>
            <div><Label>Propina (para la estilista)</Label><input type="number" className="field" value={f.tip} onChange={(e) => setF({ ...f, tip: e.target.value })} data-testid="checkout-tip" /></div>
          </div>
          {Number(f.discount) > 0 && <div><Label>Motivo del descuento</Label><input className="field" value={f.discount_reason} onChange={(e) => setF({ ...f, discount_reason: e.target.value })} data-testid="checkout-discount-reason" /></div>}
          {(cover > 0 || promo > 0) && <div className="text-xs text-muted-foreground" data-testid="checkout-breakdown">{cover > 0 && `Paquete: -${money(cover)} `}{promo > 0 && `· ${f.apply_membership ? "Membresía" : "Cupón"}: -${money(promo)}`}</div>}
          <div className="text-base">Total a cobrar: <b data-testid="checkout-total">{money(due)}</b></div>
          {due > 0 ? <PaymentRows rows={rows} setRows={setRows} total={due} /> : <div className="text-sm text-emerald-700" data-testid="checkout-nothing-due">Nada que cobrar.</div>}
          <Button className="w-full" onClick={submit} disabled={Math.abs(rows.reduce((a, r) => a + Number(r.amount || 0), 0) - due) > 0.01 || (Number(f.discount) > 0 && !f.discount_reason.trim())} data-testid="checkout-submit">Registrar cobro y marcar Atendida</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function CancelPolicyInfo({ p, apply, setApply, client }) {
  const late = p.cancel_enabled && p.hours_before < p.cancel_hours;
  if (client) return (
    <div className={`space-y-1.5 rounded-lg p-3 text-sm ${late ? "bg-amber-50 text-amber-900" : "bg-secondary/60"}`} data-testid="cancel-policy-info">
      {late && <div className="font-semibold" data-testid="cancel-late-flag">Cancelación tardía: faltan {Math.max(0, p.hours_before)} h y el salón pide cancelar con {p.cancel_hours} h de anticipación.</div>}
      <div data-testid="cancel-client-consequence">{p.client_consequence}</div>
      {p.deposit_paid > 0 && <div className="text-xs font-medium" data-testid="cancel-refund-info">Anticipo pagado Q{p.deposit_paid.toFixed(2)} · {p.refund >= p.deposit_paid ? "se le reembolsa completo" : p.refund > 0 ? `se le reembolsan Q${p.refund.toFixed(2)}` : "no se reembolsa"}.</div>}
      {p.policy_text && <div className="text-xs text-muted-foreground" data-testid="cancel-policy-text">{p.policy_text} {p.refund_text}</div>}
    </div>
  );
  return (
    <div className={`space-y-1.5 rounded-lg p-3 text-sm ${late && apply ? "bg-amber-50 text-amber-900" : "bg-secondary/60"}`} data-testid="cancel-policy-info">
      {late ? <>
        <div className="font-semibold" data-testid="cancel-late-flag">Cancelación tardía: faltan {Math.max(0, p.hours_before)} h (límite {p.cancel_hours} h).</div>
        <label className="flex items-start gap-2"><input type="checkbox" className="mt-1" checked={apply} onChange={(e) => setApply(e.target.checked)} data-testid="cancel-apply-policy" />Aplicar la política (la clienta cancela tarde). Desmárquelo si cancela el salón.</label>
        {apply && <div className="text-xs">{p.consequence}</div>}
      </> : <div>{p.cancel_enabled ? "Dentro del plazo: sin penalización." : "Política de cancelación desactivada."}</div>}
      {p.deposit_paid > 0 && <div className="text-xs font-medium" data-testid="cancel-refund-info">Anticipo recibido Q{p.deposit_paid.toFixed(2)} · reembolso: Q{(late && apply ? p.refund : p.deposit_paid).toFixed(2)}</div>}
      <div className="text-xs text-muted-foreground">Se enviará un aviso de cancelación a la clienta por WhatsApp.</div>
    </div>
  );
}

export function CancelDialog({ open, onClose, onConfirm, title = "¿Cancelar esta cita?", preview, client }) {
  const [reason, setReason] = useState("");
  const [apply, setApply] = useState(true);
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-sm" data-testid="cancel-dialog">
        <DialogHeader><DialogTitle className="font-heading">{title}</DialogTitle></DialogHeader>
        <p className="text-sm text-muted-foreground">{client ? "Si cancela, este horario quedará disponible para otras clientas." : "El horario quedará libre y se avisará a la lista de espera."}</p>
        {preview && <CancelPolicyInfo p={preview} apply={apply} setApply={setApply} client={client} />}
        <div><Label>Motivo (opcional)</Label><input className="field" value={reason} onChange={(e) => setReason(e.target.value)} data-testid="cancel-reason-input" /></div>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} data-testid="cancel-dialog-back">Volver</Button>
          <Button variant="destructive" onClick={() => { onConfirm(reason, apply); setReason(""); }} data-testid="cancel-dialog-confirm">Sí, cancelar</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
