import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { QRCodeSVG } from "qrcode.react";
import { CheckCircle2, Circle, X, AlertTriangle, Bell, Lock } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useAuth } from "@/context/Auth";
import { Panel, StatusBadge } from "@/components/Common";
import { Button } from "@/components/ui/button";

export function Onboarding() {
  const [d, setD] = useState(null);
  const { company, checkSetup } = useAuth();
  const load = () => api.get("/onboarding").then((r) => {
    setD(r.data);
    if (company && !company.setup_complete) checkSetup();
  }).catch(() => {});
  useEffect(() => { load(); }, []); // eslint-disable-line
  if (!d || d.dismissed) return null;
  const done = d.steps.filter((s) => s.done).length;
  const req = d.steps.filter((s) => d.required.includes(s.key));
  const share = async () => {
    if (!d.setup_complete) return toast.error(`Antes de compartir complete: ${d.pending.map((p) => p.label).join(", ")}`);
    await navigator.clipboard?.writeText(d.portal_url).catch(() => {});
    await api.post("/onboarding", { shared: true });
    toast.success("Enlace copiado");
    load();
  };
  const skip = async () => { try { await api.post("/onboarding", { skipped: true }); toast.success("Guía omitida: le recordaremos los pasos pendientes"); await checkSetup(); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <Panel title={`Guía de arranque · ${done}/${d.steps.length}`} className="mb-8" testid="onboarding-panel"
      action={d.setup_complete ? <button onClick={async () => { await api.post("/onboarding", { dismissed: true }); load(); }} className="text-muted-foreground" data-testid="onboarding-dismiss"><X className="h-4 w-4" /></button>
        : <Button variant="outline" size="sm" onClick={skip} data-testid="onboarding-skip">Omitir por ahora</Button>}>
      {!d.setup_complete && <p className="mb-3 text-sm text-muted-foreground" data-testid="onboarding-setup-msg">Paso {req.findIndex((s) => s.key === d.current) + 1} de {req.length}: complete cada paso en orden; al terminarlo aparece el siguiente en el menú. Al finalizar se activan la agenda, el portal de reservas y el resto del sistema.</p>}
      <div className="mb-4 h-2 rounded-full bg-slate-100"><div className="h-2 rounded-full bg-primary transition-all" style={{ width: `${(done / d.steps.length) * 100}%` }} /></div>
      <div className="grid gap-6 md:grid-cols-[1fr_auto]">
        <ul className="space-y-2">
          {d.steps.map((s, i) => {
            const locked = !d.setup_complete && !s.done && s.key !== d.current;
            const isCur = s.key === d.current;
            return (
            <li key={s.key} className={`rounded-lg text-sm ${isCur ? "bg-primary/5 px-2 py-1.5" : ""}`} data-testid={`onboarding-step-${s.key}`}>
              <div className={`flex items-center gap-2 ${isCur ? "font-semibold" : ""}`}>
              {s.done ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : locked ? <Lock className="h-4 w-4 text-slate-300" /> : <Circle className="h-4 w-4 text-primary" />}
              <span className="w-4 text-xs text-muted-foreground">{i + 1}.</span>
              {locked ? <span className="text-muted-foreground" data-testid={`onboarding-locked-${s.key}`}>{s.label}</span>
                : s.to ? <Link to={s.to} className={s.done ? "text-muted-foreground line-through" : "text-primary hover:underline"} data-testid={`onboarding-link-${s.key}`}>{s.label}{isCur && " →"}</Link>
                : <button onClick={share} className={s.done ? "text-muted-foreground line-through" : "text-primary underline"} data-testid="onboarding-share">{s.label}</button>}
              </div>
              {!s.done && !d.setup_complete && <p className="ml-10 text-xs text-muted-foreground" data-testid={`onboarding-hint-${s.key}`}>{s.hint}</p>}
            </li>
            );
          })}
        </ul>
        {d.setup_complete ? (
          <div className="text-center" data-testid="onboarding-qr">
            <QRCodeSVG value={d.portal_url} size={120} />
            <div className="mt-1 max-w-[180px] break-all text-xs">{d.portal_url}</div>
          </div>
        ) : null}
      </div>
    </Panel>
  );
}

export function PendingSteps() {
  const { setup, checkSetup } = useAuth();
  const [min, setMin] = useState(sessionStorage.getItem("pending_min") === "1");
  if (!setup?.pending?.length) return null;
  const toggle = () => { sessionStorage.setItem("pending_min", min ? "0" : "1"); setMin(!min); };
  const resume = async () => { try { await api.post("/onboarding", { skipped: false }); await checkSetup(); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <div className="mb-8 rounded-2xl border border-amber-300 bg-amber-50 p-5" data-testid="pending-steps">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-heading text-lg font-semibold text-amber-950">Pasos mínimos pendientes para dejar su salón listo ({setup.pending.length})</h3>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={resume} data-testid="pending-resume-guide">Retomar guía</Button>
          <Button size="sm" variant="ghost" onClick={toggle} data-testid="pending-minimize">{min ? "Mostrar" : "Minimizar"}</Button>
        </div>
      </div>
      {!min && <>
        <p className="mt-1 text-sm text-amber-900" data-testid="pending-portal-note">Su portal de reservas y el asistente de WhatsApp están en pausa («Este salón aún está preparando su portal») hasta completar estos pasos.</p>
        <ul className="mt-3 space-y-2">{setup.pending.map((s) => (
          <li key={s.key} className="flex flex-wrap items-center gap-2 text-sm" data-testid={`pending-step-${s.key}`}>
            <Circle className="h-4 w-4 text-amber-700" /><Link to={s.to} className="font-semibold text-amber-950 underline" data-testid={`pending-link-${s.key}`}>{s.label}</Link>
            <span className="text-xs text-amber-800">{s.hint}</span>
          </li>
        ))}</ul>
      </>}
    </div>
  );
}

export function Alerts() {
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/dashboard/alerts").then((r) => setD(r.data)).catch(() => {}); }, []);
  if (!d) return null;
  return (
    <div className="mb-8 grid gap-6 lg:grid-cols-2">
      <Panel title={`Pendientes de cerrar (${d.pending_close.length})`} testid="pending-close-panel">
        {d.pending_close.length === 0 ? <p className="text-sm text-muted-foreground">Todas las citas pasadas están cerradas.</p> : (
          <ul className="max-h-56 space-y-2 overflow-auto">{d.pending_close.map((a) => (
            <li key={a.id} className="flex items-center justify-between rounded-lg border p-2 text-sm">
              <span>{a.date} {a.time} · {a.client_name} · {a.service_name}</span><StatusBadge status={a.status} />
            </li>
          ))}</ul>
        )}
        {d.pending_close.length > 0 && <Link to="/app/agenda" className="mt-2 inline-block text-sm text-primary underline">Cerrar en la agenda</Link>}
      </Panel>
      <Panel title="Avisos" testid="alerts-panel">
        <ul className="space-y-2 text-sm">
          {d.missing_address.map((b) => <li key={b} className="flex gap-2 text-amber-800"><AlertTriangle className="h-4 w-4" />Sucursal "{b}" sin dirección: el portal y los recordatorios no la mostrarán. <Link to="/app/sucursales" className="underline">Completar</Link></li>)}
          {d.low_stock.map((p) => <li key={p.id} className="flex gap-2 text-rose-700" data-testid="low-stock-alert"><AlertTriangle className="h-4 w-4" />Existencia baja: {p.name} ({p.stock}/{p.min_stock})</li>)}
          {d.notifications.map((n) => <li key={n.id} className="flex gap-2"><Bell className="h-4 w-4 text-slate-400" /><span><b>{n.title}:</b> {n.text}</span></li>)}
          {!d.missing_address.length && !d.low_stock.length && !d.notifications.length && <li className="text-muted-foreground">Sin avisos.</li>}
        </ul>
      </Panel>
    </div>
  );
}

export function TemplatesButton({ onDone }) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const { checkSetup } = useAuth();
  const load = async () => { const r = await api.get("/service-templates"); setItems(r.data.map((x) => ({ ...x, on: false }))); setOpen(true); };
  const save = async () => {
    const sel = items.filter((x) => x.on);
    await api.post("/service-templates", { items: sel });
    toast.success(`${sel.length} servicios creados`);
    setOpen(false);
    onDone?.();
    checkSetup();
  };
  const set = (i, k, v) => setItems(items.map((x, j) => (j === i ? { ...x, [k]: v } : x)));
  return (
    <>
      <Button variant="outline" onClick={load} data-testid="service-templates-btn">Usar plantillas</Button>
      {open && createPortal(
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" onClick={() => setOpen(false)}>
          <div className="max-h-[85vh] w-full max-w-xl overflow-auto rounded-2xl bg-white p-6" onClick={(e) => e.stopPropagation()} data-testid="templates-dialog">
            <h3 className="mb-3 font-heading text-lg font-bold">Plantillas de servicios (editables)</h3>
            {items.map((x, i) => (
              <div key={x.name} className="mb-2 grid grid-cols-[auto_1fr_80px_90px] items-center gap-3 text-sm">
                <input type="checkbox" id={`tpl-${i}`} className="h-5 w-5 cursor-pointer accent-[hsl(var(--primary))]" checked={x.on} onChange={(e) => set(i, "on", e.target.checked)} data-testid={`template-check-${i}`} />
                <label htmlFor={`tpl-${i}`} className="cursor-pointer py-1">{x.name} <span className="text-xs text-muted-foreground">{x.category}</span></label>
                <input type="number" className="field h-8" value={x.duration} onChange={(e) => set(i, "duration", e.target.value)} title="Minutos" />
                <input type="number" className="field h-8" value={x.price} onChange={(e) => set(i, "price", e.target.value)} title="Precio" />
              </div>
            ))}
            <div className="mt-3 flex gap-2">
              <Button variant="outline" className="flex-1" onClick={() => setOpen(false)} data-testid="templates-cancel">Cancelar</Button>
              <Button className="flex-1" onClick={save} disabled={!items.some((x) => x.on)} data-testid="templates-save">Agregar seleccionados</Button>
            </div>
          </div>
        </div>, document.body
      )}
    </>
  );
}
