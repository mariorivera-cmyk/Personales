import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { QRCodeSVG } from "qrcode.react";
import { CheckCircle2, Circle, X, AlertTriangle, Bell } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/Auth";
import { Panel, StatusBadge } from "@/components/Common";
import { Button } from "@/components/ui/button";

export function Onboarding() {
  const [d, setD] = useState(null);
  const { company, refresh } = useAuth();
  const load = () => api.get("/onboarding").then((r) => {
    setD(r.data);
    if (r.data.setup_complete && company && !company.setup_complete) { toast.success("¡Su salón está configurado! Ya tiene acceso a todas las opciones."); refresh(); }
  }).catch(() => {});
  useEffect(() => { load(); }, []); // eslint-disable-line
  if (!d || d.dismissed) return null;
  const done = d.steps.filter((s) => s.done).length;
  const req = d.steps.filter((s) => d.required.includes(s.key));
  const share = async () => {
    await navigator.clipboard?.writeText(d.portal_url).catch(() => {});
    await api.post("/onboarding", { shared: true });
    toast.success("Enlace copiado");
    load();
  };
  return (
    <Panel title={`Guía de arranque · ${done}/${d.steps.length}`} className="mb-8" testid="onboarding-panel"
      action={d.setup_complete && <button onClick={async () => { await api.post("/onboarding", { dismissed: true }); load(); }} className="text-muted-foreground" data-testid="onboarding-dismiss"><X className="h-4 w-4" /></button>}>
      {!d.setup_complete && <p className="mb-3 text-sm text-muted-foreground" data-testid="onboarding-setup-msg">Complete los {req.length} pasos obligatorios ({req.filter((s) => s.done).length}/{req.length} listos) para activar la agenda, el portal de reservas y el resto del sistema.</p>}
      <div className="mb-4 h-2 rounded-full bg-slate-100"><div className="h-2 rounded-full bg-primary transition-all" style={{ width: `${(done / d.steps.length) * 100}%` }} /></div>
      <div className="grid gap-6 md:grid-cols-[1fr_auto]">
        <ul className="space-y-2">
          {d.steps.map((s) => (
            <li key={s.key} className="flex items-center gap-2 text-sm" data-testid={`onboarding-step-${s.key}`}>
              {s.done ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : <Circle className="h-4 w-4 text-slate-300" />}
              {s.to ? <Link to={s.to} className={s.done ? "text-muted-foreground line-through" : "hover:text-primary"}>{s.label}</Link>
                : !d.setup_complete ? <span className="text-muted-foreground">{s.label} (disponible al terminar los pasos anteriores)</span>
                : <button onClick={share} className={s.done ? "text-muted-foreground line-through" : "text-primary underline"} data-testid="onboarding-share">{s.label}</button>}
            </li>
          ))}
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
  const load = async () => { const r = await api.get("/service-templates"); setItems(r.data.map((x) => ({ ...x, on: false }))); setOpen(true); };
  const save = async () => {
    const sel = items.filter((x) => x.on);
    await api.post("/service-templates", { items: sel });
    toast.success(`${sel.length} servicios creados`);
    setOpen(false);
    onDone?.();
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
            <Button className="mt-3 w-full" onClick={save} disabled={!items.some((x) => x.on)} data-testid="templates-save">Agregar seleccionados</Button>
          </div>
        </div>, document.body
      )}
    </>
  );
}
