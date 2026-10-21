import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { Plus, Pencil, Trash2 } from "lucide-react";
import { api, errMsg, DAYS } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { PageHeader, EmptyState, Loader } from "@/components/Common";
import { useAuth } from "@/context/Auth";

const B = process.env.REACT_APP_BACKEND_URL;

function ImageInput({ id, value, onChange }) {
  const up = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    try { const r = await api.post("/company/media", fd); onChange(r.data.url); } catch (err) { toast.error(errMsg(err)); }
  };
  return (
    <div className="flex items-center gap-3">
      {value && <img src={value.startsWith("/api") ? B + value : value} alt="" className="h-14 w-14 rounded-lg object-cover" />}
      <label className="cursor-pointer rounded-full border bg-white px-3 py-1.5 text-xs hover:border-primary">Subir imagen<input type="file" accept="image/*" onChange={up} data-testid={id} className="hidden" /></label>
      {value && <button type="button" className="text-xs underline" onClick={() => onChange("")}>Quitar</button>}
    </div>
  );
}

function PkgItemsInput({ id, value, onChange }) {
  const opts = useOptions({ source: "/services" });
  const v = value || [];
  const set = (i, k, x) => onChange(v.map((r, j) => (j === i ? { ...r, [k]: x } : r)));
  return (
    <div className="space-y-1" data-testid={id}>
      {v.map((r, i) => (
        <div key={i} className="flex gap-2">
          <select className="field" value={r.service_id} onChange={(e) => set(i, "service_id", e.target.value)} data-testid={`${id}-service-${i}`}><option value="">— Servicio —</option>{opts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
          <input type="number" min="1" className="field w-24" value={r.qty} onChange={(e) => set(i, "qty", Number(e.target.value))} data-testid={`${id}-qty-${i}`} />
          <button type="button" onClick={() => onChange(v.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4 text-rose-600" /></button>
        </div>
      ))}
      <button type="button" className="text-xs text-primary" onClick={() => onChange([...v, { service_id: "", qty: 1 }])} data-testid={`${id}-add`}>+ Servicio incluido (cantidad de sesiones)</button>
    </div>
  );
}

function ConsumptionInput({ id, value, onChange }) {
  const opts = useOptions({ source: "/products" });
  const v = value || [];
  const set = (i, k, x) => onChange(v.map((r, j) => (j === i ? { ...r, [k]: x } : r)));
  return (
    <div className="space-y-1" data-testid={id}>
      {v.map((r, i) => (
        <div key={i} className="flex gap-2">
          <select className="field" value={r.product_id} onChange={(e) => set(i, "product_id", e.target.value)}><option value="">— Producto —</option>{opts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
          <input type="number" step="0.1" className="field w-24" value={r.qty} onChange={(e) => set(i, "qty", Number(e.target.value))} />
          <button type="button" onClick={() => onChange(v.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4 text-rose-600" /></button>
        </div>
      ))}
      <button type="button" className="text-xs text-primary" onClick={() => onChange([...v, { product_id: "", qty: 1 }])}>+ Producto consumido</button>
    </div>
  );
}

function useOptions(field) {
  const [opts, setOpts] = useState(field.options || []);
  useEffect(() => {
    if (!field.source) return;
    api.get(field.source).then(({ data }) =>
      setOpts(data.map((x) => ({ value: x[field.valueKey || "id"], label: x[field.labelKey || "name"] })))
    ).catch(() => {});
  }, [field.source, field.valueKey, field.labelKey]);
  return opts;
}

export function HoursEditor({ value, onChange, optional }) {
  const v = value || {};
  const own = Object.keys(v).length > 0;
  const set = (d, i, t) => {
    const cur = v[d] || ["09:00", "18:00"];
    const n = [...cur];
    n[i] = t;
    onChange({ ...v, [d]: n });
  };
  const toggle = (d) => {
    const n = { ...v };
    if (n[d]) delete n[d];
    else n[d] = ["09:00", "18:00"];
    onChange(n);
  };
  if (optional && !own)
    return (
      <button type="button" className="text-sm text-primary underline" onClick={() => onChange({ 0: ["09:00", "18:00"] })} data-testid="hours-own-btn">
        Usa horario de la sucursal · definir horario propio
      </button>
    );
  return (
    <div className="space-y-1.5" data-testid="hours-editor">
      {DAYS.map((d, i) => (
        <div key={d} className="flex items-center gap-2 text-sm">
          <label className="flex w-20 items-center gap-2">
            <input type="checkbox" checked={!!v[i]} onChange={() => toggle(String(i))} data-testid={`hours-day-${i}`} /> {d}
          </label>
          {v[i] ? (
            <>
              <input type="time" className="field h-8 w-28" value={v[i][0]} onChange={(e) => set(String(i), 0, e.target.value)} />
              <span>a</span>
              <input type="time" className="field h-8 w-28" value={v[i][1]} onChange={(e) => set(String(i), 1, e.target.value)} />
            </>
          ) : <span className="text-muted-foreground">Cerrado</span>}
        </div>
      ))}
      {optional && <button type="button" className="text-xs text-muted-foreground underline" onClick={() => onChange({})}>Usar horario de sucursal</button>}
    </div>
  );
}

export function FieldInput({ field, value, onChange }) {
  const opts = useOptions(field);
  const id = `field-${field.key}`;
  if (field.type === "textarea")
    return <textarea id={id} data-testid={id} className="field h-24 py-2" value={value || ""} onChange={(e) => onChange(e.target.value)} />;
  if (field.type === "select")
    return (
      <select id={id} data-testid={id} className="field" value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
        <option value="">{field.placeholder || "— Seleccione —"}</option>
        {opts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    );
  if (field.type === "multi")
    return (
      <div className="grid max-h-52 grid-cols-1 gap-1 overflow-auto rounded-lg border p-2 text-sm sm:grid-cols-2" data-testid={id}>
        {!opts.length && <span className="text-xs text-muted-foreground">Aún no hay opciones registradas</span>}
        {opts.map((o) => (
          <label key={o.value} className="flex cursor-pointer items-center gap-2 rounded-md px-1.5 py-1 hover:bg-secondary">
            <input type="checkbox" className="h-5 w-5 cursor-pointer accent-[hsl(var(--primary))]" data-testid={`${id}-${o.value}`} checked={(value || []).includes(o.value)}
              onChange={(e) => onChange(e.target.checked ? [...(value || []), o.value] : (value || []).filter((x) => x !== o.value))} />
            {o.label}
          </label>
        ))}
      </div>
    );
  if (field.type === "image") return <ImageInput id={id} value={value} onChange={onChange} />;
  if (field.type === "consumption") return <ConsumptionInput id={id} value={value} onChange={onChange} />;
  if (field.type === "pkgitems") return <PkgItemsInput id={id} value={value} onChange={onChange} />;
  if (field.type === "switch") return <Switch data-testid={id} checked={value !== false} onCheckedChange={onChange} />;
  if (field.type === "hours") return <HoursEditor value={value} onChange={onChange} optional={field.optional} />;
  if (field.type === "list")
    return <input id={id} data-testid={id} className="field" value={(value || []).join(", ")} placeholder={field.placeholder}
      onChange={(e) => onChange(e.target.value.split(",").map((x) => x.trim()).filter(Boolean).map((x) => (field.numeric ? Number(x) : x)))} />;
  return (
    <input id={id} data-testid={id} className="field" type={field.type || "text"} value={value ?? ""} placeholder={field.placeholder}
      onChange={(e) => onChange(field.type === "number" ? (e.target.value === "" ? "" : Number(e.target.value)) : e.target.value)} />
  );
}

export function FormDialog({ open, onOpenChange, title, fields, initial, onSubmit, testid = "form" }) {
  const [form, setForm] = useState({});
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) setForm(initial || {}); }, [open, initial]);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try { await onSubmit(form); onOpenChange(false); } catch (err) { if (err.message !== "cancelled") toast.error(errMsg(err)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-xl overflow-y-auto" data-testid={`${testid}-dialog`}>
        <DialogHeader><DialogTitle className="font-heading">{title}</DialogTitle></DialogHeader>
        <form onSubmit={submit} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {fields.filter((f) => !f.hideIf || !f.hideIf(form)).map((f) => (
            <div key={f.key} className={f.full || ["textarea", "hours", "multi", "consumption", "image", "pkgitems"].includes(f.type) ? "sm:col-span-2" : ""}>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">{f.label}</label>
              <FieldInput field={f} value={form[f.key]} onChange={(v) => setForm((s) => ({ ...s, [f.key]: v }))} />
            </div>
          ))}
          <DialogFooter className="sm:col-span-2">
            <Button type="submit" disabled={busy} data-testid={`${testid}-submit`}>{busy ? "Guardando..." : "Guardar"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default function CrudPage({ title, subtitle, endpoint, fields, columns, testid, rowActions, canWrite = true, defaults = {}, embedded, extraActions, onSaved, beforeSave }) {
  const [rows, setRows] = useState(null);
  const [edit, setEdit] = useState(null);
  const { checkSetup } = useAuth();
  const load = useCallback(() => api.get(endpoint).then(({ data }) => setRows(data)).catch((e) => { setRows([]); toast.error(errMsg(e)); }), [endpoint]);
  useEffect(() => { load(); }, [load]);
  const save = async (form) => {
    if (beforeSave && !beforeSave(form)) throw new Error("cancelled");
    if (form.id) await api.put(`${endpoint}/${form.id}`, form);
    else await api.post(endpoint, form);
    toast.success("Guardado");
    load();
    onSaved && onSaved();
    checkSetup();
  };
  const del = async (row) => {
    if (!window.confirm("¿Eliminar este registro?")) return;
    try { await api.delete(`${endpoint}/${row.id}`); toast.success("Eliminado"); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div data-testid={`${testid}-page`}>
      {!embedded && <PageHeader title={title} subtitle={subtitle} action={<>{extraActions && extraActions(load)}{canWrite && (
        <Button onClick={() => setEdit({ ...defaults })} data-testid={`${testid}-new-btn`}><Plus className="mr-1 h-4 w-4" />Nuevo</Button>)}</>} />}
      {embedded && canWrite && <div className="mb-3 flex justify-end"><Button size="sm" onClick={() => setEdit({ ...defaults })} data-testid={`${testid}-new-btn`}><Plus className="mr-1 h-4 w-4" />Nuevo</Button></div>}
      {rows === null ? <Loader /> : rows.length === 0 ? <EmptyState text={`Aún no hay registros en ${title || "esta sección"}. Cree el primero para comenzar.`}
        action={canWrite && <Button size="sm" onClick={() => setEdit({ ...defaults })} data-testid={`${testid}-empty-create`}><Plus className="mr-1 h-4 w-4" />Crear el primero</Button>} /> : (
        <div className="overflow-x-auto rounded-2xl border bg-white">
          <table className="w-full text-sm" data-testid={`${testid}-table`}>
            <thead className="bg-secondary/60 text-left text-xs uppercase tracking-wider text-slate-500">
              <tr>{columns.map((c) => <th key={c.key} className="px-4 py-3 font-semibold">{c.label}</th>)}<th className="px-4 py-3" /></tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-t transition-colors hover:bg-secondary/30" data-testid={`${testid}-row-${row.id}`}>
                  {columns.map((c) => <td key={c.key} className="px-4 py-3">{c.render ? c.render(row) : String(row[c.key] ?? "")}</td>)}
                  <td className="whitespace-nowrap px-4 py-3 text-right">
                    {rowActions && rowActions(row, load)}
                    {canWrite && <>
                      <Button variant="ghost" size="icon" onClick={() => setEdit(row)} data-testid={`${testid}-edit-${row.id}`}><Pencil className="h-4 w-4" /></Button>
                      <Button variant="ghost" size="icon" onClick={() => del(row)} data-testid={`${testid}-delete-${row.id}`}><Trash2 className="h-4 w-4 text-rose-600" /></Button>
                    </>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <FormDialog open={!!edit} onOpenChange={(o) => !o && setEdit(null)} title={edit?.id ? `Editar` : `Nuevo registro`}
        fields={fields} initial={edit} onSubmit={save} testid={testid} />
    </div>
  );
}
