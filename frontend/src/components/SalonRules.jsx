import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { RotateCcw, Lock } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Panel, Loader } from "@/components/Common";
import { useAuth } from "@/context/Auth";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";

const fmt = (d, v, services) => {
  if (d.type === "bool") return v ? "Activado" : "Desactivado";
  if (d.type === "enum") return d.options[String(v)] ?? String(v);
  if (d.type === "multi") return (v || []).map((x) => d.options[x]).join(", ") || "Ninguno";
  if (d.type === "services") return (v || []).map((id) => services.find((s) => s.id === id)?.name).filter(Boolean).join(", ") || "Ninguno";
  if (d.type === "hours") return (v || []).join(" h, ") + " h";
  if (d.type === "longtext" || d.type === "text") return v ? "Texto sugerido" : "Vacío";
  return String(v);
};

const localError = (d, v) => {
  if (!["num", "int"].includes(d.type)) return "";
  if (v === "" || v === null || v === undefined) return "No puede quedar vacío";
  const n = Number(v);
  if (Number.isNaN(n)) return "Debe ser un número";
  if (n < 0) return "No puede ser negativo";
  if (d.pct && n > 100) return "Un porcentaje no puede ser mayor a 100";
  return "";
};

function RuleInput({ d, v, set, disabled, services }) {
  const id = `rule-${d.key}`;
  if (d.type === "bool") return <Switch checked={!!v} onCheckedChange={set} disabled={disabled} data-testid={id} />;
  if (d.type === "enum") return <select className="field" value={String(v)} onChange={(e) => set(e.target.value)} disabled={disabled} data-testid={id}>{Object.entries(d.options).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>;
  const list = d.type === "multi" ? Object.entries(d.options) : d.type === "services" ? services.map((s) => [s.id, s.name]) : null;
  if (list) return (
    <div className="flex flex-wrap gap-x-4 gap-y-1" data-testid={id}>{list.map(([k, l]) => (
      <label key={k} className="flex items-center gap-1.5 text-sm"><input type="checkbox" disabled={disabled} checked={(v || []).includes(k)} onChange={(e) => set(e.target.checked ? [...(v || []), k] : (v || []).filter((x) => x !== k))} data-testid={`${id}-${k}`} />{l}</label>
    ))}{!list.length && <span className="text-xs text-muted-foreground">Aún no hay servicios</span>}</div>
  );
  if (d.type === "longtext") return <textarea className="field h-24 py-2" value={v ?? ""} onChange={(e) => set(e.target.value)} disabled={disabled} data-testid={id} />;
  if (d.type === "hours") return <input className="field" value={Array.isArray(v) ? v.join(", ") : v ?? ""} onChange={(e) => set(e.target.value)} disabled={disabled} placeholder="24, 2" data-testid={id} />;
  return <input className="field" type={d.type === "text" ? "text" : "number"} step="any" value={v ?? ""} onChange={(e) => set(e.target.value)} disabled={disabled} data-testid={id} />;
}

function RuleRow({ d, v, set, own, setOwn, branch, canEdit, services }) {
  const err = own ? localError(d, v) : "";
  return (
    <div className="grid gap-3 border-t py-4 first:border-t-0 md:grid-cols-[1fr_minmax(0,1.1fr)]" data-testid={`rule-row-${d.key}`}>
      <div>
        <div className="text-sm font-semibold">{d.label}</div>
        {d.desc && <p className="mt-0.5 text-xs text-muted-foreground">{d.desc}</p>}
        <p className="mt-1 text-[11px] uppercase tracking-wider text-slate-400" data-testid={`rule-suggested-${d.key}`}>Sugerido: {fmt(d, d.suggested, services)}</p>
      </div>
      <div className="space-y-1.5">
        {branch && <label className="flex items-center gap-2 text-xs text-muted-foreground"><input type="checkbox" checked={own} disabled={!canEdit} onChange={(e) => setOwn(e.target.checked)} data-testid={`rule-own-${d.key}`} />Regla propia de esta sucursal{!own && " (usa la general)"}</label>}
        <RuleInput d={d} v={v} set={set} disabled={!canEdit || !own} services={services} />
        {err && <p className="text-xs text-rose-600" data-testid={`rule-error-${d.key}`}>{err}</p>}
      </div>
    </div>
  );
}

export function SalonRules() {
  const [scope, setScope] = useState("");
  const [data, setData] = useState(null);
  const [vals, setVals] = useState({});
  const [own, setOwn] = useState({});
  const [services, setServices] = useState([]);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const { checkSetup } = useAuth();
  const [qp] = useSearchParams();
  const focus = qp.get("focus");
  useEffect(() => {
    if (!data || !focus) return;
    const t = setTimeout(() => {
      const el = document.querySelector(`[data-testid=rule-row-${focus}]`);
      if (!el) return;
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.classList.add("rounded-lg", "bg-amber-50", "ring-2", "ring-amber-400", "px-2");
      el.querySelector("input,select,textarea")?.focus();
    }, 300);
    return () => clearTimeout(t);
  }, [data, focus]);
  const load = (s = scope) => api.get("/salon-rules", { params: { branch_id: s } }).then((r) => {
    setData(r.data); setVals(r.data.effective);
    setOwn(Object.fromEntries(r.data.schema.map((d) => [d.key, !s || d.key in r.data.branch])));
  }).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(scope); }, [scope]); // eslint-disable-line
  useEffect(() => { api.get("/services").then((r) => setServices(r.data)).catch(() => {}); }, []);
  if (!data) return <Loader />;
  const { schema, groups, can_edit: canEdit } = data;
  const conv = (d, v) => (d.type === "hours" && typeof v === "string" ? v.split(",").map((x) => x.trim()).filter(Boolean) : v);
  const save = async () => {
    const bad = schema.find((d) => own[d.key] && localError(d, vals[d.key]));
    if (bad) return toast.error(`«${bad.label}»: ${localError(bad, vals[bad.key])}`);
    const values = {};
    schema.forEach((d) => {
      const changed = JSON.stringify(vals[d.key]) !== JSON.stringify(data.effective[d.key]);
      if (!scope) { if (changed) values[d.key] = conv(d, vals[d.key]); return; }
      if (own[d.key] && (changed || !(d.key in data.branch))) values[d.key] = conv(d, vals[d.key]);
      if (!own[d.key] && d.key in data.branch) values[d.key] = null;
    });
    if (!Object.keys(values).length) {
      if (data.reviewed) return toast.info("No hay cambios por guardar");
      try { await api.post("/salon-rules/reviewed"); toast.success("Reglas sugeridas confirmadas"); load(); checkSetup(); } catch (e) { toast.error(errMsg(e)); }
      return;
    }
    setBusy(true);
    try { await api.put("/salon-rules", { branch_id: scope, values }); toast.success("Reglas guardadas: aplican a las nuevas reservas"); load(); checkSetup(); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const reset = async () => {
    try { await api.post("/salon-rules/reset", { branch_id: scope }); toast.success(scope ? "La sucursal vuelve a usar las reglas generales" : "Valores sugeridos restaurados"); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  const toggleOwn = (k, on) => { setOwn({ ...own, [k]: on }); if (!on) setVals({ ...vals, [k]: data.effective[k] }); };
  return (
    <div data-testid="salon-rules">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="max-w-2xl text-sm text-muted-foreground">Defina cómo trabaja su salón. Los cambios aplican a las reservas nuevas; las citas ya creadas conservan la regla con la que se hicieron.</p>
          {!canEdit && <p className="mt-2 flex items-center gap-1.5 text-sm font-medium text-amber-800" data-testid="rules-readonly"><Lock className="h-4 w-4" />Solo lectura: únicamente un administrador puede cambiar las reglas.</p>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select className="field w-56" value={scope} onChange={(e) => setScope(e.target.value)} data-testid="rules-scope-select">
            <option value="">General (todo el salón)</option>
            {data.branches.map((b) => <option key={b.id} value={b.id}>Sucursal: {b.name}</option>)}
          </select>
          {canEdit && <Button variant="outline" onClick={() => setConfirm(true)} data-testid="rules-reset-btn"><RotateCcw className="mr-1 h-4 w-4" />{scope ? "Usar reglas generales" : "Restaurar sugeridos"}</Button>}
          {canEdit && <Button onClick={save} disabled={busy} data-testid="rules-save-btn">{busy ? "Guardando..." : data.reviewed ? "Guardar reglas" : "Guardar y confirmar reglas"}</Button>}
        </div>
      </div>
      <div className="grid gap-6 xl:grid-cols-2">
        {Object.entries(groups).map(([g, title]) => (
          <Panel key={g} title={`${g}. ${title}`} testid={`rules-group-${g}`}>
            {schema.filter((d) => d.group === g).map((d) => (
              <RuleRow key={d.key} d={d} v={vals[d.key]} set={(v) => setVals({ ...vals, [d.key]: v })} own={own[d.key]} setOwn={(on) => toggleOwn(d.key, on)} branch={!!scope} canEdit={canEdit} services={services} />
            ))}
            {g === "E" && <p className="pt-2 text-xs text-muted-foreground">Excepciones: defina el % o monto propio de cada estilista en Estilistas y de cada servicio en Servicios.</p>}
          </Panel>
        ))}
      </div>
      <AlertDialog open={confirm} onOpenChange={setConfirm}>
        <AlertDialogContent data-testid="rules-reset-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>{scope ? "¿Quitar las reglas propias de esta sucursal?" : "¿Restaurar los valores sugeridos?"}</AlertDialogTitle>
            <AlertDialogDescription>{scope ? "La sucursal volverá a usar las reglas generales del salón." : "Todas las reglas generales vuelven a su valor inicial. Las citas ya creadas no cambian."}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="rules-reset-cancel">Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={reset} data-testid="rules-reset-confirm">Sí, restaurar</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
