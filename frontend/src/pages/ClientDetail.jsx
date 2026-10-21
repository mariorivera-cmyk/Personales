import { useEffect, useState, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, Upload, FileText, Trash2, Sparkles } from "lucide-react";
import { api, errMsg, money } from "@/lib/api";
import { useAuth } from "@/context/Auth";
import { PageHeader, Kpi, Panel, StatusBadge, Label } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { AppointmentForm } from "@/components/AppointmentForm";
import { ClientPackagesPanel } from "@/components/PackageParts";

export default function ClientDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const [d, setD] = useState(null);
  const [f, setF] = useState({});
  const [booking, setBooking] = useState(false);
  const load = useCallback(() => api.get(`/clients/${id}`).then((r) => { setD(r.data); setF(r.data.client); }).catch((e) => toast.error(errMsg(e))), [id]);
  useEffect(() => { load(); }, [load]);
  if (!d) return <div className="text-muted-foreground">Cargando...</div>;
  const canEdit = true;
  const canBook = user.role !== "stylist";
  const save = async () => {
    try { await api.put(`/clients/${id}`, f); toast.success("Ficha actualizada"); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  const upload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    fd.append("kind", e.target.dataset.kind);
    try { await api.post(`/clients/${id}/files`, fd); toast.success("Archivo cargado"); load(); } catch (err) { toast.error(errMsg(err)); }
  };
  const openFile = async (fl) => {
    const r = await api.get(`/files/${fl.id}`, { responseType: "blob" });
    window.open(URL.createObjectURL(r.data), "_blank");
  };
  const delFile = async (fl) => { await api.delete(`/files/${fl.id}`); load(); };
  const s = d.stats;
  const notes = f.notes || {};
  return (
    <div data-testid="client-detail-page">
      <Link to="/app/clientes" className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-primary"><ArrowLeft className="h-4 w-4" />Clientes</Link>
      <PageHeader title={d.client.name} subtitle={`${d.client.phone} · ${d.client.points || 0} puntos${d.client.membership ? ` · Membresía ${d.client.membership}` : ""}`}
        action={canBook && <Button onClick={() => setBooking(true)} data-testid="client-book-btn">Agendar cita</Button>} />
      {notes.allergies && <div className="mb-6 rounded-2xl border border-rose-300 bg-rose-50 p-4 text-sm font-semibold text-rose-800" data-testid="client-allergy-banner">Alergias: {notes.allergies}</div>}
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-5">
        <Kpi label="Visitas" value={s.visits} testid="client-visits" />
        <Kpi label="Gasto acumulado" value={money(s.spent)} testid="client-spent" />
        <Kpi label="Frecuencia" value={s.frequency_days ? `${s.frequency_days} días` : "—"} testid="client-frequency" />
        <Kpi label="Citas futuras" value={s.future} testid="client-future" />
        <Kpi label="Cancelaciones / No show" value={`${s.cancellations} / ${s.no_shows}`} hint={s.late_cancels ? `${s.late_cancels} cancelación(es) tardía(s)` : undefined} testid="client-cancellations" />
      </div>
      {d.recommendations.length > 0 && (
        <div className="mb-6 flex items-start gap-2 rounded-2xl border border-primary/30 bg-primary/5 p-4 text-sm" data-testid="client-recommendations">
          <Sparkles className="mt-0.5 h-4 w-4 text-primary" /><div>{d.recommendations.map((r) => <div key={r.service_id}>{r.message}</div>)}</div>
        </div>
      )}
      <div className="grid gap-6 lg:grid-cols-3">
        <Panel title="Datos básicos" testid="client-basic-panel">
          <div className="space-y-3">
            {[["name", "Nombre"], ["email", "Correo", "email"], ["birthdate", "Nacimiento", "date"], ["membership", "Membresía"]].map(([k, l, t]) => (
              <div key={k}><Label>{l}</Label><input className="field" type={t || "text"} disabled={!canEdit} value={f[k] || ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} data-testid={`client-${k}-input`} /></div>
            ))}
            <div><Label>Género</Label><select className="field" disabled={!canEdit} value={f.gender || ""} onChange={(e) => setF({ ...f, gender: e.target.value })} data-testid="client-gender-select">
              <option value="">—</option><option value="F">Femenino</option><option value="M">Masculino</option><option value="O">Otro</option></select></div>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.photo_consent !== false} onChange={(e) => setF({ ...f, photo_consent: e.target.checked })} data-testid="client-photo-consent" />Autoriza fotografías</label>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!f.no_whatsapp} onChange={(e) => setF({ ...f, no_whatsapp: e.target.checked })} data-testid="client-no-whatsapp" />No tiene WhatsApp (avisos por correo)</label>
            {f.data_consent && <p className="text-xs text-muted-foreground">Consentimiento de datos: {String(f.data_consent).slice(0, 10)}</p>}
          </div>
        </Panel>
        <Panel title="Notas internas (cifradas)" testid="client-notes-panel">
          <div className="space-y-3">
            {[["allergies", "Alergias"], ["color_formulas", "Fórmulas de color"], ["preferences", "Preferencias"], ["restrictions", "Restricciones"], ["observations", "Notas privadas"]].map(([k, l]) => (
              <div key={k}><Label>{l}</Label><textarea className="field h-20 py-2" disabled={!canEdit} value={notes[k] || ""} onChange={(e) => setF({ ...f, notes: { ...notes, [k]: e.target.value } })} data-testid={`client-note-${k}`} /></div>
            ))}
            {canEdit && <Button onClick={save} className="w-full" data-testid="client-save-btn">Guardar ficha</Button>}
          </div>
        </Panel>
        <Panel title="Archivos" testid="client-files-panel">
          {canEdit && <div className="mb-3 flex flex-wrap gap-2">
            {[["antes", "Foto antes"], ["despues", "Foto después"], ["consentimiento", "Consentimiento"], ["documento", "Documento"]].map(([k, l]) => (
              <label key={k} className="inline-flex cursor-pointer items-center gap-1 rounded-full border bg-white px-3 py-1.5 text-xs hover:border-primary">
                <Upload className="h-3.5 w-3.5" />{l}<input type="file" className="hidden" data-kind={k} onChange={upload} data-testid={`upload-${k}`} />
              </label>
            ))}
          </div>}
          <ul className="space-y-2">
            {d.files.map((fl) => (
              <li key={fl.id} className="flex items-center justify-between rounded-lg border p-2 text-sm">
                <button className="flex items-center gap-2 truncate hover:text-primary" onClick={() => openFile(fl)}><FileText className="h-4 w-4" />{fl.name}<span className="text-xs text-muted-foreground">({fl.kind})</span></button>
                {canEdit && <button onClick={() => delFile(fl)}><Trash2 className="h-4 w-4 text-rose-600" /></button>}
              </li>
            ))}
            {d.files.length === 0 && <li className="text-sm text-muted-foreground">Sin archivos</li>}
          </ul>
        </Panel>
      </div>
      {canBook && <ClientPackagesPanel client={d.client} />}
      <Panel title="Historial de citas" className="mt-6" testid="client-history">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-slate-500"><tr><th className="py-2">Fecha</th><th>Servicio</th><th>Estilista</th><th>Sucursal</th><th>Monto</th><th>Estado</th></tr></thead>
            <tbody>{d.appointments.map((a) => (
              <tr key={a.id} className="border-t"><td className="py-2">{a.date} {a.time}</td><td>{a.service_name}{a.addon_names?.length ? ` + ${a.addon_names.join(", ")}` : ""}</td><td>{a.stylist_name}</td><td>{a.branch_name}</td><td>{money(a.price)}</td><td><StatusBadge status={a.status} /></td></tr>
            ))}</tbody>
          </table>
        </div>
      </Panel>
      <Dialog open={booking} onOpenChange={setBooking}>
        <DialogContent className="max-h-[92vh] max-w-2xl overflow-y-auto"><DialogHeader><DialogTitle>Agendar para {d.client.name}</DialogTitle></DialogHeader>
          <AppointmentForm defaultDate={new Date().toISOString().slice(0, 10)} client={d.client} onDone={() => { setBooking(false); load(); }} />
        </DialogContent>
      </Dialog>
    </div>
  );
}
