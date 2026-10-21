import { useEffect, useMemo, useState, useCallback, useRef } from "react";
import { toast } from "sonner";
import { ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { api, errMsg, money, todayStr, addDays, DAYS, STATUS } from "@/lib/api";
import { useAuth } from "@/context/Auth";
import { PageHeader, StatusBadge, Label } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { AppointmentForm, Alternatives } from "@/components/AppointmentForm";
import { CheckoutDialog, CancelDialog } from "@/components/Checkout";
import { STATUS_CLS } from "@/lib/api";

const nowGT = () => new Date(new Date().toLocaleString("en-US", { timeZone: "America/Guatemala" }));

const PX = 1.5;
const hm = (t) => `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`;

const START = 8 * 60, END = 20 * 60;
const wd = (d) => (new Date(d + "T12:00:00").getDay() + 6) % 7;
const mins = (s) => { const [h, m] = s.split(":").map(Number); return h * 60 + m; };
const COLORS = ["#2E1A47", "#059669", "#E0900A", "#E11D48", "#0369A1", "#7A4FB0"];

function range(view, date) {
  if (view === "day") return [date, date];
  if (view === "week") { const s = addDays(date, -wd(date)); return [s, addDays(s, 6)]; }
  const s = date.slice(0, 8) + "01";
  const e = new Date(+date.slice(0, 4), +date.slice(5, 7), 0).toISOString().slice(0, 10);
  return [s, e];
}

function workMinutes(st, branch, date) {
  const d = String(wd(date));
  const bh = branch?.hours?.[d];
  if (!bh) return 0;
  const sh = st.hours && Object.keys(st.hours).length ? st.hours[d] : bh;
  if (!sh) return 0;
  return Math.max(0, Math.min(mins(bh[1]), mins(sh[1])) - Math.max(mins(bh[0]), mins(sh[0])));
}

function DayView({ appts, stylists, branches, date, onOpen, onMove }) {
  const hours = [];
  for (let h = START; h < END; h += 60) hours.push(h);
  return (
    <div className="overflow-x-auto rounded-2xl border bg-white" data-testid="agenda-day-view">
      <div className="flex min-w-max">
        <div className="w-14 shrink-0 border-r pt-16">
          {hours.map((h) => <div key={h} className="h-[90px] pr-2 text-right text-[11px] text-muted-foreground">{String(h / 60).padStart(2, "0")}:00</div>)}
        </div>
        {stylists.map((st, i) => {
          const mine = appts.filter((a) => a.stylist_id === st.id && !["cancelled"].includes(a.status));
          const work = workMinutes(st, branches.find((b) => b.id === st.branch_id), date);
          const booked = mine.filter((a) => a.status !== "no_show").reduce((s, a) => s + a.duration, 0);
          const occ = work ? Math.round((booked / work) * 100) : 0;
          return (
            <div key={st.id} className="w-48 shrink-0 border-r last:border-r-0" data-testid={`agenda-col-${st.id}`}>
              <div className="sticky top-0 h-16 border-b bg-secondary/40 px-3 py-2">
                <div className="truncate text-sm font-semibold">{st.name}</div>
                <div className="mt-1 h-1.5 rounded-full bg-slate-200"><div className="h-1.5 rounded-full bg-primary" style={{ width: `${Math.min(occ, 100)}%` }} /></div>
                <div className="text-[11px] text-muted-foreground">Ocupación {occ}%</div>
              </div>
              <div className="relative" style={{ height: (END - START) * PX }} onDragOver={(e) => e.preventDefault()} data-testid={`agenda-drop-${st.id}`}
                onDrop={(e) => { const y = e.clientY - e.currentTarget.getBoundingClientRect().top - Number(e.dataTransfer.getData("dy") || 0); onMove(e.dataTransfer.getData("id"), st.id, hm(START + Math.max(0, Math.round(y / PX / 30)) * 30)); }}>
                {hours.map((h) => <div key={h} className="h-[90px] border-b border-dashed border-slate-100" />)}
                {mine.map((a) => (
                  <button key={a.id} onClick={() => onOpen(a)} data-testid={`appt-${a.id}`} draggable={a.status !== "completed"}
                    onDragStart={(e) => { e.dataTransfer.setData("id", a.id); e.dataTransfer.setData("dy", String(e.clientY - e.currentTarget.getBoundingClientRect().top)); }}
                    className={`absolute left-1 right-1 overflow-hidden rounded-lg border border-l-4 p-1.5 text-left text-[11px] leading-tight shadow-sm transition-transform hover:z-10 hover:scale-[1.02] ${STATUS_CLS[a.status]}`}
                    style={{ top: (mins(a.time) - START) * PX, minHeight: Math.max(a.duration * PX, 48), borderLeftColor: COLORS[i % COLORS.length] }}>
                    <div className="font-semibold">{a.time} {a.client_name}</div>
                    <div className="truncate">{a.service_name}{a.addon_names?.length ? ` + ${a.addon_names.join(", ")}` : ""}</div>
                    <div className="text-[10px] font-semibold opacity-80">{STATUS[a.status]}{a.deposit_status === "pending" ? " · anticipo pendiente" : ""}</div>
                  </button>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function WeekView({ appts, start, onOpen, onDay }) {
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-7" data-testid="agenda-week-view">
      {DAYS.map((d, i) => {
        const date = addDays(start, i);
        const list = appts.filter((a) => a.date === date);
        return (
          <div key={d} className="min-h-40 rounded-2xl border bg-white p-3">
            <button className="mb-2 text-sm font-semibold hover:text-primary" onClick={() => onDay(date)}>{d} {date.slice(8)}</button>
            <div className="space-y-1.5">
              {list.map((a) => (
                <button key={a.id} onClick={() => onOpen(a)} className="block w-full rounded-md bg-secondary/60 p-1.5 text-left text-[11px] hover:bg-secondary" data-testid={`appt-${a.id}`}>
                  <b>{a.time}</b> {a.client_name}<div className="truncate text-muted-foreground">{a.service_name} · {a.stylist_name}</div>
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function MonthView({ appts, start, onDay }) {
  const first = wd(start);
  const days = new Date(+start.slice(0, 4), +start.slice(5, 7), 0).getDate();
  const cells = [...Array(first).fill(null), ...Array.from({ length: days }, (_, i) => addDays(start, i))];
  return (
    <div className="rounded-2xl border bg-white p-4" data-testid="agenda-month-view">
      <div className="grid grid-cols-7 gap-2 text-center text-xs font-semibold text-slate-500">{DAYS.map((d) => <div key={d}>{d}</div>)}</div>
      <div className="mt-2 grid grid-cols-7 gap-2">
        {cells.map((c, i) => {
          if (!c) return <div key={i} />;
          const n = appts.filter((a) => a.date === c && a.status !== "cancelled").length;
          return (
            <button key={c} onClick={() => onDay(c)} className={`h-20 rounded-xl border p-2 text-left transition-colors hover:border-primary ${c === todayStr() ? "border-primary" : ""}`} data-testid={`month-day-${c}`}>
              <div className="text-sm font-semibold">{+c.slice(8)}</div>
              {n > 0 && <div className="mt-1 inline-block rounded-full bg-primary/10 px-2 text-xs text-primary">{n} citas</div>}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function ApptDialog({ appt, onClose, reload, canEdit }) {
  const [res, setRes] = useState({});
  const [alts, setAlts] = useState(null);
  const [checkout, setCheckout] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [info, setInfo] = useState(null);
  const [preview, setPreview] = useState(null);
  const { user } = useAuth();
  const future = appt && new Date(`${appt.date}T${appt.time}:00`) > nowGT();
  const openCancel = () => api.get(`/appointments/${appt.id}/cancel-preview`).then((r) => { setPreview(r.data); setCancelOpen(true); }).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { if (appt) api.get("/clients/lookup", { params: { phone: appt.client_phone } }).then((r) => setInfo(r.data)).catch(() => setInfo(null)); }, [appt]);
  useEffect(() => { if (appt) { setRes({ date: appt.date, time: appt.time }); setAlts(null); } }, [appt]);
  if (!appt) return null;
  const status = async (s, reason = "", apply = false) => {
    try { const r = await api.post(`/appointments/${appt.id}/status`, { status: s, reason, apply_policy: apply }); toast.success(s === "cancelled" && r.data.late_cancel ? "Cita cancelada: registrada como cancelación tardía" : `Cita: ${STATUS[s]}`); reload(); onClose(); } catch (e) { toast.error(errMsg(e)); }
  };
  const deposit = async () => {
    try { await api.post(`/appointments/${appt.id}/deposit`, {}); toast.success("Anticipo recibido: cita confirmada"); reload(); onClose(); } catch (e) { toast.error(errMsg(e)); }
  };
  const resched = async () => {
    try { await api.post(`/appointments/${appt.id}/reschedule`, res); toast.success("Cita reprogramada"); reload(); onClose(); }
    catch (e) { toast.error(errMsg(e)); setAlts(e.response?.data?.detail?.alternatives); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg" data-testid="appt-dialog">
        <DialogHeader><DialogTitle className="font-heading">{appt.client_name}</DialogTitle></DialogHeader>
        <div className="space-y-1 text-sm">
          <div className="flex items-center gap-2"><StatusBadge status={appt.status} /><span className="text-muted-foreground">Origen: {appt.source}</span></div>
          <div><b>{appt.service_name}</b>{appt.addon_names?.length ? ` + ${appt.addon_names.join(", ")}` : ""}</div>
          <div>{appt.date} · {appt.time} – {appt.end_time} · {appt.stylist_name} · {appt.branch_name}</div>
          {appt.status === "cancelled" && <div data-testid="appt-cancel-type" className={appt.late_cancel ? "font-semibold text-amber-800" : "text-muted-foreground"}>{appt.late_cancel ? "Cancelación tardía" : appt.cancel_type === "salon" ? "Cancelada por el salón" : "Cancelada a tiempo"}{appt.cancel_reason ? ` · ${appt.cancel_reason}` : ""}{appt.deposit_refund !== undefined ? ` · Reembolso Q${Number(appt.deposit_refund).toFixed(2)}` : ""}</div>}
          <div>Total {money(appt.price)} · Anticipo requerido {money(appt.deposit_required)} · Tel. {appt.client_phone}</div>
        </div>
        {canEdit && appt.status !== "cancelled" && <>
          {info?.allergies && <div className="rounded-lg bg-rose-50 p-2 text-sm font-semibold text-rose-700" data-testid="appt-allergy-alert">Alergias: {info.allergies}</div>}
          {info?.alert && <div className="rounded-lg bg-amber-50 p-2 text-sm text-amber-900">Esta clienta tiene {info.no_shows} faltas registradas.</div>}
          <div className="flex flex-wrap gap-2">
            {appt.deposit_status === "pending" && <Button size="sm" onClick={deposit} data-testid="appt-deposit-received">Anticipo recibido</Button>}
            {appt.status !== "completed" ? <>
              {appt.status === "pending" && <Button size="sm" variant="outline" onClick={() => status("confirmed")} data-testid="appt-status-confirmed">Confirmar</Button>}
              <Button size="sm" onClick={() => setCheckout(true)} disabled={future} title={future ? "La cita aún no empieza" : ""} data-testid="appt-status-completed">Atendida</Button>
              <Button size="sm" variant="outline" onClick={() => status("no_show")} data-testid="appt-status-no_show">No asistió</Button>
              <Button size="sm" variant="destructive" onClick={openCancel} data-testid="appt-status-cancelled">Cancelar</Button>
              {future && <span className="w-full text-xs text-muted-foreground" data-testid="appt-future-hint">«Atendida» se habilita a la hora de inicio ({appt.time}).</span>}
            </> : user.role === "company_admin" ? <Button size="sm" variant="outline" onClick={() => status("confirmed", "Corrección de administrador")} data-testid="appt-reopen">Corregir (reabrir)</Button>
              : <span className="text-xs text-muted-foreground">Cita atendida: solo un administrador puede corregirla.</span>}
          </div>
          <div className="grid grid-cols-3 items-end gap-2 border-t pt-3">
            <div><Label>Fecha</Label><input type="date" className="field" value={res.date || ""} onChange={(e) => setRes({ ...res, date: e.target.value })} data-testid="resched-date" /></div>
            <div><Label>Hora</Label><input type="time" step="1800" className="field" value={res.time || ""} onChange={(e) => setRes({ ...res, time: e.target.value })} data-testid="resched-time" /></div>
            <Button onClick={resched} data-testid="resched-submit">Reprogramar</Button>
          </div>
          {alts && <Alternatives alts={alts} onPick={(s) => setRes({ ...res, time: s.time, date: s.date || res.date, stylist_id: s.stylist_id })} />}
        </>}
        {checkout && <CheckoutDialog appt={appt} onClose={() => setCheckout(false)} onDone={() => { setCheckout(false); reload(); onClose(); }} />}
        <CancelDialog open={cancelOpen} preview={preview} onClose={() => setCancelOpen(false)} onConfirm={(r, apply) => { setCancelOpen(false); status("cancelled", r, apply); }} />
      </DialogContent>
    </Dialog>
  );
}

export default function Agenda() {
  const { user } = useAuth();
  const [view, setView] = useState("day");
  const [date, setDate] = useState(todayStr());
  const [branch, setBranch] = useState("");
  const [appts, setAppts] = useState([]);
  const [branches, setBranches] = useState([]);
  const [stylists, setStylists] = useState([]);
  const [open, setOpen] = useState(null);
  const [creating, setCreating] = useState(false);
  const [s, e] = range(view, date);
  const canEdit = user.role !== "stylist";
  const reqId = useRef(0);
  const load = useCallback(() => {
    const id = ++reqId.current;
    api.get("/appointments", { params: { start: s, end: e, branch_id: branch } }).then((r) => { if (id === reqId.current) setAppts(r.data); }).catch((x) => toast.error(errMsg(x)));
  }, [s, e, branch]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api.get("/branches").then((r) => { setBranches(r.data); if (user.role === "branch_manager") setBranch(user.branch_id || ""); });
    api.get("/stylists").then((r) => setStylists(r.data));
  }, [user]);
  const cols = useMemo(() => {
    let l = stylists.filter((x) => x.active !== false && (!branch || x.branch_id === branch));
    if (user.role === "stylist") l = l.filter((x) => x.id === user.stylist_id);
    return l;
  }, [stylists, branch, user]);
  const move = async (id, stylistId, time) => {
    const a = appts.find((x) => x.id === id);
    if (!a || (a.time === time && a.stylist_id === stylistId)) return;
    try { await api.post(`/appointments/${id}/reschedule`, { date: a.date, time, stylist_id: stylistId }); toast.success(`Cita movida a las ${time}`); load(); }
    catch (e) { toast.error(errMsg(e)); }
  };
  const step = view === "day" ? 1 : view === "week" ? 7 : 30;
  const branchOcc = branches.filter((b) => !branch || b.id === branch).map((b) => {
    const work = stylists.filter((x) => x.branch_id === b.id && x.active !== false).reduce((t, x) => t + workMinutes(x, b, date), 0);
    const booked = appts.filter((a) => a.branch_id === b.id && a.date === date && !["cancelled", "no_show"].includes(a.status)).reduce((t, a) => t + a.duration, 0);
    return { name: b.name, occ: work ? Math.round((booked / work) * 100) : 0 };
  });
  return (
    <div data-testid="agenda-page">
      <PageHeader title="Agenda inteligente" subtitle="Vista consolidada por estilista y sucursal"
        action={canEdit && <Button onClick={() => setCreating(true)} data-testid="new-appointment-btn"><Plus className="mr-1 h-4 w-4" />Nueva cita</Button>} />
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="flex rounded-full border bg-white p-1 text-sm">
          {[["day", "Día"], ["week", "Semana"], ["month", "Mes"]].map(([k, l]) => (
            <button key={k} onClick={() => setView(k)} className={`rounded-full px-4 py-1.5 transition-colors ${view === k ? "bg-primary text-white" : ""}`} data-testid={`view-${k}-btn`}>{l}</button>
          ))}
        </div>
        <Button variant="outline" size="icon" onClick={() => setDate(addDays(date, -step))} data-testid="agenda-prev"><ChevronLeft className="h-4 w-4" /></Button>
        <input type="date" className="field w-40" value={date} onChange={(ev) => setDate(ev.target.value)} data-testid="agenda-date" />
        <Button variant="outline" size="icon" onClick={() => setDate(addDays(date, step))} data-testid="agenda-next"><ChevronRight className="h-4 w-4" /></Button>
        <Button variant="ghost" onClick={() => setDate(todayStr())}>Hoy</Button>
        {user.role !== "stylist" && (
          <select className="field w-48" value={branch} onChange={(ev) => setBranch(ev.target.value)} data-testid="agenda-branch-filter">
            <option value="">Todas las sucursales</option>
            {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        )}
        {view === "day" && <div className="ml-auto flex gap-3 text-xs" data-testid="branch-occupancy">{branchOcc.map((b) => <span key={b.name} className="rounded-full bg-white px-3 py-1 border">{b.name}: <b>{b.occ}%</b></span>)}</div>}
      </div>
      <div className="mb-3 flex flex-wrap gap-2 text-[11px]" data-testid="status-legend">{Object.entries(STATUS).filter(([k]) => k !== "in_progress").map(([k, l]) => <span key={k} className={`rounded-full border px-2 py-0.5 ${STATUS_CLS[k]}`}>{l}</span>)}{view === "day" && canEdit && <span className="text-muted-foreground">Arrastre una cita para moverla de horario o estilista.</span>}</div>
      {view === "day" && <DayView appts={appts} stylists={cols} branches={branches} date={date} onOpen={setOpen} onMove={canEdit ? move : () => {}} />}
      {view === "week" && <WeekView appts={appts} start={s} onOpen={setOpen} onDay={(d) => { setDate(d); setView("day"); }} />}
      {view === "month" && <MonthView appts={appts} start={s} onDay={(d) => { setDate(d); setView("day"); }} />}
      <ApptDialog appt={open} onClose={() => setOpen(null)} reload={load} canEdit={canEdit} />
      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent className="max-h-[92vh] max-w-2xl overflow-y-auto" data-testid="new-appointment-dialog">
          <DialogHeader><DialogTitle className="font-heading">Nueva cita</DialogTitle></DialogHeader>
          <AppointmentForm defaultDate={date} onDone={() => { setCreating(false); load(); }} />
        </DialogContent>
      </Dialog>
    </div>
  );
}
