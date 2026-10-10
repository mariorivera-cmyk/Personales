import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { Plus, Pencil, Trash2 } from "lucide-react";
import { api, errMsg, DAYS } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { PageHeader, EmptyState } from "@/components/Common";

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
      <div className="grid max-h-40 grid-cols-2 gap-1 overflow-auto rounded-lg border p-2 text-sm" data-testid={id}>
        {opts.map((o) => (
          <label key={o.value} className="flex items-center gap-2">
            <input type="checkbox" checked={(value || []).includes(o.value)}
              onChange={(e) => onChange(e.target.checked ? [...(value || []), o.value] : (value || []).filter((x) => x !== o.value))} />
            {o.label}
          </label>
        ))}
      </div>
    );
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
    try { await onSubmit(form); onOpenChange(false); } catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-xl overflow-y-auto" data-testid={`${testid}-dialog`}>
        <DialogHeader><DialogTitle className="font-heading">{title}</DialogTitle></DialogHeader>
        <form onSubmit={submit} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {fields.filter((f) => !f.hideIf || !f.hideIf(form)).map((f) => (
            <div key={f.key} className={f.full || ["textarea", "hours", "multi"].includes(f.type) ? "sm:col-span-2" : ""}>
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

export default function CrudPage({ title, subtitle, endpoint, fields, columns, testid, rowActions, canWrite = true, defaults = {}, embedded }) {
  const [rows, setRows] = useState([]);
  const [edit, setEdit] = useState(null);
  const load = useCallback(() => api.get(endpoint).then(({ data }) => setRows(data)).catch((e) => toast.error(errMsg(e))), [endpoint]);
  useEffect(() => { load(); }, [load]);
  const save = async (form) => {
    if (form.id) await api.put(`${endpoint}/${form.id}`, form);
    else await api.post(endpoint, form);
    toast.success("Guardado");
    load();
  };
  const del = async (row) => {
    if (!window.confirm("¿Eliminar este registro?")) return;
    try { await api.delete(`${endpoint}/${row.id}`); toast.success("Eliminado"); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div data-testid={`${testid}-page`}>
      {!embedded && <PageHeader title={title} subtitle={subtitle} action={canWrite && (
        <Button onClick={() => setEdit({ ...defaults })} data-testid={`${testid}-new-btn`}><Plus className="mr-1 h-4 w-4" />Nuevo</Button>)} />}
      {embedded && canWrite && <div className="mb-3 flex justify-end"><Button size="sm" onClick={() => setEdit({ ...defaults })} data-testid={`${testid}-new-btn`}><Plus className="mr-1 h-4 w-4" />Nuevo</Button></div>}
      {rows.length === 0 ? <EmptyState text="Aún no hay registros." /> : (
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
