import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { toast } from "sonner";
import { Clock, MapPin, Sparkles, CheckCircle2, MessageCircle } from "lucide-react";
import { api, errMsg, money, todayStr } from "@/lib/api";
import { Label } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Alternatives } from "@/components/AppointmentForm";

const HERO = "https://images.unsplash.com/photo-1633681926022-84c23e8cb2d6?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600";

function MyAppointments({ slug }) {
  const [phone, setPhone] = useState("");
  const [list, setList] = useState(null);
  const [res, setRes] = useState({});
  const find = async () => { const r = await api.post(`/public/salon/${slug}/my`, { phone }); setList(r.data); };
  const manage = async (a, action) => {
    try {
      await api.post(`/public/salon/${slug}/appointments/${a.id}`, { phone, action, ...(res[a.id] || {}) });
      toast.success(action === "cancel" ? "Cita cancelada" : action === "confirm" ? "Cita confirmada" : "Cita reprogramada");
      find();
    } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <section className="rounded-3xl border bg-white p-6" data-testid="my-appointments">
      <h2 className="font-heading text-xl font-bold">Mis citas</h2>
      <div className="mt-3 flex gap-2"><input className="field" placeholder="Su teléfono" value={phone} onChange={(e) => setPhone(e.target.value)} data-testid="my-phone-input" /><Button onClick={find} data-testid="my-find-btn">Buscar</Button></div>
      {list && (list.length === 0 ? <p className="mt-3 text-sm text-muted-foreground">No hay citas próximas.</p> : (
        <ul className="mt-4 space-y-3">{list.map((a) => (
          <li key={a.id} className="rounded-xl border p-3 text-sm" data-testid={`my-appt-${a.id}`}>
            <div className="font-medium">{a.service_name} · {a.date} {a.time}</div><div className="text-muted-foreground">{a.stylist_name} · {a.branch_name}</div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <input type="date" className="field h-8 w-36" onChange={(e) => setRes({ ...res, [a.id]: { ...res[a.id], date: e.target.value } })} />
              <input type="time" step="1800" className="field h-8 w-28" onChange={(e) => setRes({ ...res, [a.id]: { ...res[a.id], time: e.target.value } })} />
              <Button size="sm" variant="outline" onClick={() => manage(a, "reschedule")} data-testid={`my-resched-${a.id}`}>Reprogramar</Button>
              <Button size="sm" variant="outline" onClick={() => manage(a, "confirm")}>Confirmar</Button>
              <Button size="sm" variant="destructive" onClick={() => manage(a, "cancel")} data-testid={`my-cancel-${a.id}`}>Cancelar</Button>
            </div>
          </li>
        ))}</ul>
      ))}
    </section>
  );
}

export default function PublicBooking() {
  const { slug } = useParams();
  const [salon, setSalon] = useState(null);
  const [error, setError] = useState("");
  const [f, setF] = useState({ date: todayStr(), addon_ids: [] });
  const [data, setData] = useState(null);
  const [done, setDone] = useState(null);
  const [busy, setBusy] = useState(false);
  const [fav, setFav] = useState(null);
  useEffect(() => {
    api.get(`/public/salon/${slug}`).then((r) => { setSalon(r.data); setF((x) => ({ ...x, branch_id: r.data.branches[0]?.id })); }).catch((e) => setError(errMsg(e)));
  }, [slug]);
  useEffect(() => {
    if (!f.service_id || !f.branch_id || !f.date) return;
    api.get(`/public/salon/${slug}/slots`, { params: { branch_id: f.branch_id, service_id: f.service_id, date: f.date, stylist_id: f.pref === "choose" ? f.stylist_id || "" : "" } }).then((r) => setData(r.data));
  }, [slug, f.service_id, f.branch_id, f.date, f.stylist_id, f.pref]);
  useEffect(() => {
    const digits = (f.phone || "").replace(/\D/g, "");
    if (digits.length < 8) { setFav(null); return; }
    const t = setTimeout(() => {
      api.post(`/public/salon/${slug}/last-stylist`, { phone: f.phone, service_id: f.service_id }).then((r) => setFav(r.data)).catch(() => setFav(null));
    }, 400);
    return () => clearTimeout(t);
  }, [slug, f.phone, f.service_id]);
  if (error) return <div className="grid min-h-screen place-items-center p-6 text-center" data-testid="portal-error"><div><div className="font-display text-3xl italic">Portal no disponible</div><p className="mt-2 text-muted-foreground">{error}</p></div></div>;
  if (!salon) return null;
  const cur = salon.currency;
  const svc = salon.services.find((s) => s.id === f.service_id);
  const sugg = data?.suggestions || [];
  const total = (svc?.price || 0) + sugg.filter((s) => f.addon_ids.includes(s.service.id)).reduce((a, s) => a + s.service.price, 0);
  const times = data ? [...new Map(data.slots.map((s) => [s.time, s])).values()] : [];
  const book = async () => {
    setBusy(true);
    try { const r = await api.post(`/public/salon/${slug}/book`, f); setDone(r.data); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const waitlist = async () => {
    if (!f.phone || !f.name) return toast.error("Ingrese nombre y teléfono");
    try { await api.post(`/public/salon/${slug}/waitlist`, f); toast.success("Le avisaremos por WhatsApp si se libera un espacio"); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div className="min-h-screen" data-testid="public-portal">
      <header className="fixed top-0 z-50 w-full border-b bg-[#FAF7F2]/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3"><div className="font-display text-xl italic">{salon.name}</div>
          {salon.whatsapp_number && <a href={`https://wa.me/${salon.whatsapp_number.replace("+", "")}`} className="flex items-center gap-1 text-sm text-[#128C7E]" data-testid="portal-whatsapp-link"><MessageCircle className="h-4 w-4" />WhatsApp</a>}</div>
      </header>
      <section className="relative h-[52vh] min-h-[360px]">
        <img src={HERO} alt="Salón" className="absolute inset-0 h-full w-full object-cover" />
        <div className="absolute inset-0 bg-gradient-to-r from-slate-900/80 via-slate-900/40 to-transparent" />
        <div className="relative mx-auto flex h-full max-w-6xl flex-col justify-end px-6 pb-12 text-white">
          <h1 className="max-w-2xl text-4xl font-extrabold tracking-tight sm:text-5xl lg:text-6xl fade-up">{salon.name}</h1>
          <p className="mt-3 max-w-lg text-white/85 fade-up-2">{salon.portal?.tagline || "Reserva tu cita en segundos"}</p>
        </div>
      </section>
      <main className="mx-auto grid max-w-6xl gap-8 px-6 py-12 lg:grid-cols-[1fr_380px]">
        {done ? (
          <section className="rounded-3xl border bg-white p-10 text-center lg:col-span-2" data-testid="booking-success">
            <CheckCircle2 className="mx-auto h-12 w-12 text-emerald-600" />
            <h2 className="mt-3 font-heading text-2xl font-bold">¡Cita reservada!</h2>
            <p className="mt-2 text-muted-foreground">{done.service_name}{done.addon_names.length ? ` + ${done.addon_names.join(", ")}` : ""} · {done.date} a las {done.time} con {done.stylist_name} en {done.branch_name}.</p>
            {done.deposit_required > 0 && <p className="mt-2 text-sm">Anticipo requerido: <b>{money(done.deposit_required, cur)}</b> (el salón le enviará el enlace de pago).</p>}
            <p className="mt-2 text-sm">Le enviamos la confirmación por WhatsApp.</p>
            <Button className="mt-6 rounded-full" onClick={() => { setDone(null); setF({ ...f, time: "", addon_ids: [] }); }}>Reservar otra cita</Button>
          </section>
        ) : (<>
          <div className="space-y-8">
            <section>
              <h2 className="mb-4 font-heading text-xl font-bold">1. Elija su servicio</h2>
              <div className="grid gap-3 sm:grid-cols-2">
                {salon.services.map((s) => (
                  <button key={s.id} onClick={() => setF({ ...f, service_id: s.id, time: "", addon_ids: [] })} data-testid={`portal-service-${s.id}`}
                    className={`rounded-2xl border bg-white p-4 text-left transition-all hover:-translate-y-0.5 ${f.service_id === s.id ? "border-primary ring-2 ring-primary/30" : ""}`}>
                    <div className="flex justify-between"><span className="font-semibold">{s.name}</span><span className="font-semibold text-primary">{money(s.price, cur)}</span></div>
                    <div className="mt-1 flex items-center gap-1 text-xs text-muted-foreground"><Clock className="h-3 w-3" />{s.duration} min · {s.category}</div>
                  </button>
                ))}
              </div>
            </section>
            {f.service_id && <section className="fade-up">
              <h2 className="mb-4 font-heading text-xl font-bold">2. Sucursal, estilista y fecha</h2>
              <div className="grid gap-3 sm:grid-cols-3">
                <div><Label>Sucursal</Label><select className="field" value={f.branch_id} onChange={(e) => setF({ ...f, branch_id: e.target.value, stylist_id: "", pref: "", time: "" })} data-testid="portal-branch-select">{salon.branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></div>
                <div><Label>Fecha</Label><input type="date" min={todayStr()} className="field" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value, time: "" })} data-testid="portal-date-input" /></div>
              </div>
              {fav?.eligible && f.stylist_id !== fav.stylist_id && (
                <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-primary/30 bg-primary/5 p-4 text-sm" data-testid="portal-favorite-banner">
                  <span>¿Desea agendar nuevamente con <b>{fav.stylist_name}</b>, quien le atendió la última vez?</span>
                  <Button size="sm" className="rounded-full" onClick={() => setF({ ...f, pref: "choose", branch_id: fav.branch_id, stylist_id: fav.stylist_id, time: "" })} data-testid="portal-favorite-accept">Sí, con {fav.stylist_name.split(" ")[0]}</Button>
                </div>
              )}
              <div className="mt-4" data-testid="portal-stylist-choice">
                <Label>¿Tiene un estilista de preferencia?</Label>
                <div className="flex flex-wrap gap-2">
                  {[["choose", "Sí, quiero elegir"], ["any", "Asígnenme según disponibilidad"]].map(([k, l]) => (
                    <button key={k} type="button" onClick={() => setF({ ...f, pref: k, stylist_id: "", time: "" })} data-testid={`portal-pref-${k}`}
                      className={`rounded-full border px-4 py-1.5 text-sm transition-colors ${f.pref === k ? "border-slate-900 bg-slate-900 text-white" : "bg-white hover:border-primary"}`}>{l}</button>
                  ))}
                </div>
                {f.pref === "choose" && (
                  <select className="field mt-3 max-w-xs" value={f.stylist_id || ""} onChange={(e) => setF({ ...f, stylist_id: e.target.value, time: "" })} data-testid="portal-stylist-select">
                    <option value="">— Seleccione estilista —</option>
                    {salon.stylists.filter((s) => s.branch_id === f.branch_id).map((s) => <option key={s.id} value={s.id}>{s.name}{s.specialties ? ` · ${s.specialties}` : ""}</option>)}
                  </select>
                )}
              </div>
              {(f.pref === "any" || (f.pref === "choose" && f.stylist_id)) && <div className="mt-4">
                {times.length > 0 ? <div className="flex flex-wrap gap-2">{times.map((s) => (
                  <button key={s.time} onClick={() => setF({ ...f, time: s.time, stylist_id: f.pref === "choose" ? f.stylist_id : s.stylist_id })} data-testid={`portal-slot-${s.time}`}
                    className={`rounded-full border px-4 py-1.5 text-sm transition-colors ${f.time === s.time ? "border-primary bg-primary text-white" : "bg-white hover:border-primary"}`}>{s.time}</button>
                ))}</div> : data && <>
                  <Alternatives alts={data.alternatives} onPick={(s) => setF({ ...f, time: s.time, stylist_id: s.stylist_id, date: s.date || f.date, branch_id: s.branch_id || f.branch_id })} />
                  {salon.waitlist && <Button variant="outline" className="mt-3" onClick={waitlist} data-testid="portal-waitlist-btn">Unirme a la lista de espera</Button>}
                </>}
                {f.pref === "any" && f.time && <p className="mt-2 text-sm text-muted-foreground" data-testid="portal-assigned-stylist">Le atenderá: <b>{salon.stylists.find((s) => s.id === f.stylist_id)?.name}</b></p>}
              </div>}
            </section>}
            {sugg.length > 0 && f.time && <section className="rounded-2xl border border-primary/30 bg-primary/5 p-5 fade-up" data-testid="portal-suggestions">
              <div className="mb-2 flex items-center gap-1 font-semibold text-primary"><Sparkles className="h-4 w-4" />Complemente su visita</div>
              {sugg.map((s) => (
                <label key={s.rule_id} className="flex items-center justify-between py-1 text-sm">
                  <span className="flex items-center gap-2"><input type="checkbox" checked={f.addon_ids.includes(s.service.id)} data-testid={`portal-suggestion-${s.service.id}`}
                    onChange={(e) => setF({ ...f, addon_ids: e.target.checked ? [...f.addon_ids, s.service.id] : f.addon_ids.filter((x) => x !== s.service.id), rec_type: e.target.checked ? s.type : null })} />{s.message || s.service.name}</span>
                  <span>+{money(s.service.price, cur)}</span>
                </label>
              ))}
            </section>}
          </div>
          <aside className="h-fit space-y-4 rounded-3xl border bg-white p-6 lg:sticky lg:top-20" data-testid="portal-summary">
            <h2 className="font-heading text-xl font-bold">Sus datos</h2>
            <p className="text-xs text-muted-foreground">Si ya nos visitó, escriba su teléfono y le sugeriremos a su estilista.</p>
            {[["name", "Nombre completo"], ["phone", "Teléfono WhatsApp"], ["email", "Correo (opcional)"], ["referred_by", "¿Quién le refirió? (teléfono, opcional)"]].map(([k, l]) => (
              <div key={k}><Label>{l}</Label><input className="field" value={f[k] || ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} data-testid={`portal-${k}-input`} /></div>
            ))}
            <div className="space-y-1 border-t pt-3 text-sm">
              <div>{svc?.name || "Seleccione un servicio"}</div>
              {f.time && <div className="flex items-center gap-1 text-muted-foreground"><MapPin className="h-3.5 w-3.5" />{salon.branches.find((b) => b.id === f.branch_id)?.name} · {f.date} {f.time}</div>}
              <div className="text-lg font-bold" data-testid="portal-total">{money(total, cur)}</div>
            </div>
            <Button className="w-full rounded-full" disabled={busy || !f.time || !f.name || !f.phone} onClick={book} data-testid="portal-book-btn">{busy ? "Reservando..." : "Confirmar reserva"}</Button>
          </aside>
        </>)}
        <div className="lg:col-span-2"><MyAppointments slug={slug} /></div>
      </main>
    </div>
  );
}
