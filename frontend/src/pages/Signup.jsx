import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { toast } from "sonner";
import { Check } from "lucide-react";
import { api, errMsg, money } from "@/lib/api";
import { useAuth } from "@/context/Auth";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/Common";

export function CardForm({ value, onChange }) {
  return (
    <div className="grid grid-cols-2 gap-3" data-testid="card-form">
      <div className="col-span-2"><Label>Número de tarjeta</Label>
        <input className="field" placeholder="4242 4242 4242 4242" value={value.number || ""} onChange={(e) => onChange({ ...value, number: e.target.value })} data-testid="card-number-input" /></div>
      <div><Label>Vence (MM/AA)</Label><input className="field" placeholder="12/29" value={value.exp || ""} onChange={(e) => onChange({ ...value, exp: e.target.value })} data-testid="card-exp-input" /></div>
      <div><Label>CVC</Label><input className="field" placeholder="123" value={value.cvc || ""} onChange={(e) => onChange({ ...value, cvc: e.target.value })} data-testid="card-cvc-input" /></div>
      <p className="col-span-2 text-xs text-muted-foreground">Pasarela SIMULADA: la tarjeta se tokeniza y no se almacena. Use una terminada en 0002 para simular rechazo.</p>
    </div>
  );
}

export default function Signup() {
  const nav = useNavigate();
  const { setToken } = useAuth();
  const [data, setData] = useState({ plans: [], modules: [], settings: {} });
  const [f, setF] = useState({ billing_cycle: "monthly", modules: [], currency: "GTQ" });
  const [card, setCard] = useState({});
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.get("/public/plans").then((r) => { setData(r.data); setF((s) => ({ ...s, plan_id: r.data.plans[1]?.id })); }); }, []);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const plan = data.plans.find((p) => p.id === f.plan_id);
  const extras = data.modules.filter((m) => plan && !plan.included_modules.includes(m.key) && m.price_monthly > 0);
  const monthly = (plan?.price_monthly || 0) + extras.filter((m) => f.modules.includes(m.key)).reduce((a, m) => a + m.price_monthly, 0);
  const total = f.billing_cycle === "annual" ? monthly * 12 * (1 - (data.settings.annual_discount || 0) / 100) : monthly;
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      let c = null;
      if (card.number) {
        const t = await api.post("/gateway/tokenize", card);
        c = { token: t.data.token, last4: t.data.last4, brand: t.data.brand, exp: t.data.exp };
      }
      const r = await api.post("/signup", { ...f, card: c });
      await setToken(r.data.token);
      toast.success("¡Empresa registrada! Su periodo de prueba ha iniciado.");
      nav("/app");
    } catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); }
  };
  return (
    <div className="min-h-screen px-4 py-10 sm:px-8">
      <form onSubmit={submit} className="mx-auto max-w-5xl space-y-8" data-testid="signup-form">
        <div className="fade-up">
          <Link to="/login" className="font-display text-2xl italic text-primary">SalonFlow</Link>
          <h1 className="mt-4 text-4xl font-extrabold tracking-tight sm:text-5xl">Registre su salón</h1>
          <p className="mt-2 text-muted-foreground">{data.settings.trial_days} días de prueba gratis. Sin compromiso.</p>
        </div>
        <section className="grid gap-4 rounded-2xl border bg-white p-6 sm:grid-cols-2 fade-up-2">
          {[["company_name", "Nombre comercial"], ["nit", "NIT"], ["contact_name", "Nombre de contacto"], ["email", "Correo", "email"],
            ["password", "Contraseña", "password"], ["phone", "Teléfono"], ["whatsapp_number", "Número WhatsApp del salón"], ["slug", "Enlace del portal (ej. misalon)"]].map(([k, l, t]) => (
            <div key={k}><Label>{l}</Label><input className="field" type={t || "text"} required={["company_name", "email", "password"].includes(k)} value={f[k] || ""} onChange={set(k)} data-testid={`signup-${k}-input`} /></div>
          ))}
        </section>
        <section className="fade-up-3">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold">Plan</h2>
            <div className="flex rounded-full border bg-white p-1 text-sm">
              {[["monthly", "Mensual"], ["annual", `Anual (-${data.settings.annual_discount || 0}%)`]].map(([k, l]) => (
                <button type="button" key={k} onClick={() => setF({ ...f, billing_cycle: k })} data-testid={`cycle-${k}-btn`}
                  className={`rounded-full px-4 py-1.5 transition-colors ${f.billing_cycle === k ? "bg-primary text-white" : ""}`}>{l}</button>
              ))}
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            {data.plans.map((p) => (
              <button type="button" key={p.id} onClick={() => setF({ ...f, plan_id: p.id, modules: [] })} data-testid={`plan-card-${p.name}`}
                className={`rounded-2xl border bg-white p-6 text-left transition-all hover:-translate-y-0.5 ${f.plan_id === p.id ? "border-primary ring-2 ring-primary/30" : ""}`}>
                <div className="font-heading text-xl font-bold">{p.name}</div>
                <div className="mt-2 text-3xl font-extrabold">{money(p.price_monthly)}<span className="text-sm font-normal text-muted-foreground">/mes</span></div>
                <ul className="mt-4 space-y-1 text-sm">
                  {p.included_modules.map((k) => <li key={k} className="flex items-center gap-2"><Check className="h-3.5 w-3.5 text-emerald-600" />{data.modules.find((m) => m.key === k)?.name}</li>)}
                  <li className="text-muted-foreground">{p.max_branches} sucursal(es) · {p.max_stylists} estilistas</li>
                </ul>
              </button>
            ))}
          </div>
        </section>
        {extras.length > 0 && (
          <section className="rounded-2xl border bg-white p-6">
            <h2 className="mb-3 text-lg font-semibold">Módulos adicionales</h2>
            <div className="grid gap-2 sm:grid-cols-2">
              {extras.map((m) => (
                <label key={m.key} className="flex items-center justify-between rounded-lg border p-3 text-sm">
                  <span className="flex items-center gap-2"><input type="checkbox" checked={f.modules.includes(m.key)} data-testid={`module-check-${m.key}`}
                    onChange={(e) => setF({ ...f, modules: e.target.checked ? [...f.modules, m.key] : f.modules.filter((x) => x !== m.key) })} />{m.name}</span>
                  <span className="text-muted-foreground">+{money(m.price_monthly)}/mes</span>
                </label>
              ))}
            </div>
          </section>
        )}
        <section className="grid gap-6 rounded-2xl border bg-white p-6 md:grid-cols-2">
          <div>
            <h2 className="mb-3 text-lg font-semibold">Método de pago</h2>
            <CardForm value={card} onChange={setCard} />
            <div className="mt-3"><Label>Cupón</Label><input className="field" value={f.coupon_code || ""} onChange={set("coupon_code")} data-testid="signup-coupon-input" /></div>
          </div>
          <div className="flex flex-col justify-between rounded-xl bg-slate-900 p-6 text-white">
            <div>
              <div className="text-xs uppercase tracking-widest text-slate-400">Total después de la prueba</div>
              <div className="mt-2 text-4xl font-extrabold" data-testid="signup-total">{money(total)}</div>
              <div className="text-sm text-slate-400">{f.billing_cycle === "annual" ? "por año" : "por mes"} + IVA ({data.settings.tax_rate}%)</div>
            </div>
            <label className="mt-6 flex items-start gap-2 text-sm">
              <input type="checkbox" checked={!!f.accept_terms} onChange={(e) => setF({ ...f, accept_terms: e.target.checked })} data-testid="signup-terms-checkbox" />
              Acepto los términos y condiciones del servicio y la política de tratamiento de datos.
            </label>
            <Button type="submit" className="mt-4 rounded-full" disabled={busy} data-testid="signup-submit-button">{busy ? "Creando..." : "Crear cuenta e iniciar prueba"}</Button>
          </div>
        </section>
      </form>
    </div>
  );
}
