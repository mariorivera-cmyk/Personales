import { useEffect, useState } from "react";
import { toast } from "sonner";
import { es } from "date-fns/locale";
import { api, errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";

const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const parse = (s) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };

function SlotButtons({ slots, pick, setPick, testid }) {
  return (
    <div className="flex flex-wrap gap-2" data-testid={testid}>
      {slots.map((s) => {
        const on = pick && pick.time === s.time && pick.stylist_id === s.stylist_id;
        return <button key={`${s.time}-${s.stylist_id}`} type="button" onClick={() => setPick(s)} data-testid={`resched-slot-${s.time.replace(":", "")}-${s.stylist_id}`}
          className={`rounded-full border px-3 py-1.5 text-sm transition-colors ${on ? "border-primary bg-primary text-primary-foreground" : "hover:bg-secondary"}`}>{s.time}{testid === "resched-others" && <span className="ml-1 text-xs opacity-75">· {s.stylist_name}</span>}</button>;
      })}
    </div>
  );
}

export function RescheduleDialog({ slug, appt, hdr, onClose, onDone }) {
  const [info, setInfo] = useState(null);
  const [date, setDate] = useState(null);
  const [day, setDay] = useState(null);
  const [pick, setPick] = useState(null);
  const [busy, setBusy] = useState(false);
  const base = `/public/salon/${slug}/appointments/${appt.id}/slots`;
  useEffect(() => { api.get(base, hdr()).then((r) => setInfo(r.data)).catch((e) => { toast.error(errMsg(e)); onClose(); }); }, []); // eslint-disable-line
  useEffect(() => {
    if (!date) return;
    setDay(null); setPick(null);
    api.get(base, { ...hdr(), params: { date } }).then((r) => setDay(r.data)).catch((e) => toast.error(errMsg(e)));
  }, [date]); // eslint-disable-line
  const save = async () => {
    setBusy(true);
    try {
      await api.post(`/public/salon/${slug}/appointments/${appt.id}`, { action: "reschedule", date, time: pick.time, stylist_id: pick.stylist_id }, hdr());
      toast.success(`Cita reprogramada para el ${date} a las ${pick.time}`); onDone(); onClose();
    } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const disabled = (d) => !info || ymd(d) < info.min_date.slice(0, 10) || ymd(d) > info.max_date || info.holidays.includes(ymd(d));
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[92vh] max-w-md overflow-y-auto" data-testid="resched-dialog">
        <DialogHeader><DialogTitle>Reprogramar {appt.service_name}</DialogTitle>
          <DialogDescription>Cita actual: {appt.date} a las {appt.time} con {appt.stylist_name}.</DialogDescription></DialogHeader>
        {info && <p className="rounded-lg bg-secondary/60 p-2 text-xs" data-testid="resched-rule">Puede reprogramar hasta {info.reschedule_hours} h antes, máximo {info.max_reschedules} {info.max_reschedules === 1 ? "vez" : "veces"} por cita (lleva {info.count}).</p>}
        {info && !info.allowed ? <p className="text-sm font-medium text-rose-700" data-testid="resched-not-allowed">Esta cita ya no se puede reprogramar en línea. Comuníquese con el salón.</p> : <>
          <Calendar mode="single" locale={es} selected={date ? parse(date) : undefined} onSelect={(d) => d && setDate(ymd(d))} disabled={disabled}
            fromDate={info ? parse(info.min_date) : undefined} toDate={info ? parse(info.max_date) : undefined} className="mx-auto rounded-xl border" data-testid="resched-calendar" />
          {date && !day && <p className="text-center text-sm text-muted-foreground">Buscando horarios…</p>}
          {day && <div className="space-y-3 text-sm">
            {day.own.length > 0 && <div><p className="mb-1.5 font-medium">Horarios con {day.stylist_name}</p><SlotButtons slots={day.own} pick={pick} setPick={setPick} testid="resched-own" /></div>}
            {!day.own.length && day.others.length > 0 && <div><p className="mb-1.5 font-medium" data-testid="resched-others-msg">{day.stylist_name} no tiene espacio ese día. Disponible con otra estilista:</p><SlotButtons slots={day.others} pick={pick} setPick={setPick} testid="resched-others" /></div>}
            {!day.own.length && !day.others.length && <div data-testid="resched-no-slots"><p className="mb-1.5 font-medium">Ese día no hay espacio. Próximos días con horario:</p>
              <div className="flex flex-wrap gap-2">{day.next_days.map((n) => <Button key={n.date} size="sm" variant="outline" onClick={() => setDate(n.date)} data-testid={`resched-next-${n.date}`}>{n.date} ({n.count})</Button>)}
                {!day.next_days.length && <span className="text-muted-foreground">No encontramos horarios cercanos; comuníquese con el salón.</span>}</div></div>}
          </div>}
        </>}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} data-testid="resched-cancel">Cancelar</Button>
          <Button onClick={save} disabled={!pick || busy} data-testid="resched-confirm">{pick ? `Confirmar ${date} ${pick.time}` : "Elija un horario"}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
