import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Sparkles } from "lucide-react";
import { api, errMsg, money, todayStr } from "@/lib/api";
import { Label } from "@/components/Common";
import { Button } from "@/components/ui/button";

export function Alternatives({ alts, onPick, title = "Horario no disponible. Alternativas:" }) {
  if (!alts) return null;
  const chip = (s, label, k) => (
    <button key={k} type="button" onClick={() => onPick(s)} className="rounded-full border bg-white px-3 py-1 text-xs hover:border-primary" data-testid={`alt-${k}`}>{label}</button>
  );
  return (
    <div className="space-y-2 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm" data-testid="alternatives-box">
      {title && <div className="font-semibold text-amber-900" data-testid="alternatives-title">{title}</div>}
      {alts.same_day?.length > 0 && <div className="flex flex-wrap gap-1.5">{alts.same_day.map((s, i) => chip(s, `${s.time} · ${s.stylist_name}`, `same-${i}`))}</div>}
      {alts.other_stylists?.length > 0 && <div><div className="text-xs text-muted-foreground">Otros estilistas</div><div className="flex flex-wrap gap-1.5">{alts.other_stylists.map((s, i) => chip(s, `${s.stylist_name} ${s.time}`, `sty-${i}`))}</div></div>}
      {alts.other_branches?.length > 0 && <div><div className="text-xs text-muted-foreground">Otras sucursales</div><div className="flex flex-wrap gap-1.5">{alts.other_branches.map((s, i) => chip(s, `${s.branch_name} ${s.time}`, `br-${i}`))}</div></div>}
      {alts.next_days?.length > 0 && <div><div className="text-xs text-muted-foreground">Próximos días</div><div className="flex flex-wrap gap-1.5">{alts.next_days.flatMap((d, j) => d.slots.slice(0, 2).map((s, i) => chip({ ...s, date: d.date }, `${d.date.slice(5)} ${s.time}`, `day-${j}-${i}`)))}</div></div>}
    </div>
  );
}

export function AppointmentForm({ defaultDate, onDone, client }) {
  const [opts, setOpts] = useState({ branches: [], services: [], stylists: [] });
  const [f, setF] = useState({ date: defaultDate, phone: client?.phone || "", name: client?.name || "", addon_ids: [] });
  const [slots, setSlots] = useState(null);
  const [sugg, setSugg] = useState([]);
  const [busy, setBusy] = useState(false);
  const [info, setInfo] = useState(null);
  useEffect(() => {
    const digits = (f.phone || "").replace(/\D/g, "");
    if (digits.length < 8) { setInfo(null); return; }
    const t = setTimeout(() => api.get("/clients/lookup", { params: { phone: f.phone } }).then((r) => {
      setInfo(r.data);
      if (r.data.exists) setF((x) => ({ ...x, name: x.name || r.data.client.name }));
    }).catch(() => {}), 400);
    return () => clearTimeout(t);
  }, [f.phone]);
  const phoneOk = /^\+?\d{8,15}$/.test((f.phone || "").replace(/[\s-]/g, ""));
  useEffect(() => {
    Promise.all([api.get("/branches"), api.get("/services"), api.get("/stylists")]).then(([b, s, st]) => {
      setOpts({ branches: b.data, services: s.data.filter((x) => x.active !== false), stylists: st.data });
      setF((x) => ({ ...x, branch_id: b.data[0]?.id }));
    });
  }, []);
  useEffect(() => {
    if (!f.branch_id || !f.service_id || !f.date) return;
    api.get("/availability", { params: { branch_id: f.branch_id, service_id: f.service_id, date: f.date, stylist_id: f.stylist_id || "" } })
      .then((r) => setSlots(r.data)).catch((e) => toast.error(errMsg(e)));
  }, [f.branch_id, f.service_id, f.date, f.stylist_id]);
  useEffect(() => {
    if (!f.service_id) return;
    api.get("/suggestions", { params: { service_id: f.service_id } }).then((r) => setSugg(r.data)).catch(() => setSugg([]));
    setF((x) => ({ ...x, addon_ids: [], rec_type: null }));
  }, [f.service_id]);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value, ...(k !== "time" ? { time: k === "stylist_id" ? f.time : "" } : {}) });
  const toggleAddon = (sg) => {
    const on = f.addon_ids.includes(sg.service.id);
    setF({ ...f, addon_ids: on ? f.addon_ids.filter((x) => x !== sg.service.id) : [...f.addon_ids, sg.service.id], rec_type: on ? null : sg.type });
  };
  const submit = async () => {
    setBusy(true);
    try {
      await api.post("/appointments", f);
      toast.success("Cita agendada y confirmación enviada por WhatsApp");
      onDone?.();
    } catch (e) {
      toast.error(errMsg(e));
      const alts = e.response?.data?.detail?.alternatives;
      if (alts) setSlots({ slots: [], alternatives: alts });
    } finally { setBusy(false); }
  };
  const svc = opts.services.find((x) => x.id === f.service_id);
  const total = (svc?.price || 0) + sugg.filter((s) => f.addon_ids.includes(s.service.id)).reduce((a, s) => a + s.service.price, 0);
  const uniqueTimes = slots ? [...new Map(slots.slots.map((s) => [s.time + s.stylist_id, s])).values()] : [];
  return (
    <div className="space-y-4" data-testid="appointment-form">
      <div className="grid grid-cols-2 gap-3">
        <div><Label>Teléfono cliente</Label><input className="field" value={f.phone} onChange={set("phone")} placeholder="+502..." data-testid="appt-phone-input" /></div>
        <div><Label>Nombre</Label><input className="field" value={f.name} onChange={set("name")} data-testid="appt-name-input" /></div>
        <div><Label>Sucursal</Label><select className="field" value={f.branch_id || ""} onChange={set("branch_id")} data-testid="appt-branch-select">{opts.branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></div>
        <div><Label>Servicio</Label><select className="field" value={f.service_id || ""} onChange={set("service_id")} data-testid="appt-service-select"><option value="">— Seleccione —</option>{opts.services.map((s) => <option key={s.id} value={s.id}>{s.name} · {s.duration}min · {money(s.price)}</option>)}</select></div>
        <div><Label>Estilista (opcional)</Label><select className="field" value={f.stylist_id || ""} onChange={set("stylist_id")} data-testid="appt-stylist-select"><option value="">Cualquiera disponible</option>{opts.stylists.filter((s) => s.branch_id === f.branch_id).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
        <div><Label>Fecha</Label><input type="date" className="field" value={f.date} onChange={set("date")} data-testid="appt-date-input" /></div>
      </div>
      {f.phone && !phoneOk && <p className="text-xs text-rose-600" data-testid="appt-phone-error">Teléfono inválido: use código de país y número, ej. +50255551234</p>}
      {info?.exists && <div className="rounded-xl border bg-secondary/50 p-3 text-sm" data-testid="client-found">Clienta existente: <b>{info.client.name}</b> · Faltas: {info.no_shows}
        {info.alert && <div className="mt-1 font-semibold text-rose-700" data-testid="noshow-alert">Alcanza el límite de {info.max_no_shows} faltas ({info.no_shows}). Regla del salón: {info.noshow_action}.</div>}
        {info.deposit_next && <div className="mt-1 font-semibold text-amber-800" data-testid="deposit-next-alert">Canceló tarde: esta reserva requiere anticipo.</div>}
        {info.allergies && <div className="mt-1 font-semibold text-rose-700" data-testid="allergy-alert">Alergias: {info.allergies}</div>}</div>}
      {info && !info.exists && phoneOk && <p className="text-xs text-muted-foreground">Clienta nueva: se creará su ficha.</p>}
      {slots && (
        <div>
          <Label>Horarios disponibles</Label>
          {uniqueTimes.length === 0 ? <Alternatives alts={slots.alternatives} title={f.date === todayStr() ? "Hoy ya no hay turnos, estos son los próximos:" : undefined} onPick={(s) => setF({ ...f, time: s.time, stylist_id: s.stylist_id, date: s.date || f.date, branch_id: s.branch_id || f.branch_id })} /> : (
            <div className="flex max-h-40 flex-wrap gap-1.5 overflow-auto">
              {uniqueTimes.map((s) => (
                <button key={s.time + s.stylist_id} type="button" onClick={() => setF({ ...f, time: s.time, stylist_id: s.stylist_id })} data-testid={`slot-${s.time}-${s.stylist_id}`}
                  className={`rounded-full border px-3 py-1 text-xs transition-colors ${f.time === s.time && f.stylist_id === s.stylist_id ? "border-primary bg-primary text-white" : "bg-white hover:border-primary"}`}>
                  {s.time} · {s.stylist_name.split(" ")[0]}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      {sugg.length > 0 && (
        <div className="space-y-2 rounded-xl border border-primary/30 bg-primary/5 p-3" data-testid="suggestions-box">
          <div className="flex items-center gap-1 text-sm font-semibold text-primary"><Sparkles className="h-4 w-4" />Sugerencias para aumentar el ticket</div>
          {sugg.map((s) => (
            <label key={s.rule_id} className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-2"><input type="checkbox" checked={f.addon_ids.includes(s.service.id)} onChange={() => toggleAddon(s)} data-testid={`suggestion-${s.service.id}`} />
                <span className="rounded bg-white px-1.5 text-[10px] uppercase">{s.type === "cross" ? "Cross" : "Upsell"}</span>{s.message || s.service.name}</span>
              <span>+{money(s.service.price)}</span>
            </label>
          ))}
        </div>
      )}
      <div className="flex items-center justify-between border-t pt-3">
        <div className="text-sm">Total estimado: <b data-testid="appt-total">{money(total)}</b></div>
        <Button onClick={submit} disabled={busy || !f.time || !phoneOk} data-testid="appt-submit-btn">{busy ? "Agendando..." : `Agendar ${f.time || ""}`}</Button>
      </div>
    </div>
  );
}
