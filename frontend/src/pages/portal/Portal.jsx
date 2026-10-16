import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { toast } from "sonner";
import { Clock, Sparkles, CheckCircle2, MessageCircle, Star, CalendarPlus, Download } from "lucide-react";
import { api, errMsg, money, todayStr, API } from "@/lib/api";
import { Label, Loader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Alternatives } from "@/components/AppointmentForm";
import { SalonInfo, Footer, MyAccount, img } from "@/pages/portal/PortalParts";

const HERO = "https://images.unsplash.com/photo-1633681926022-84c23e8cb2d6?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600";
const CODES = ["+502", "+503", "+504", "+505", "+506", "+507", "+52", "+1", "+57", "+34"];

const gcal = (a, salon) => {
  const f = (d, h) => d.replace(/-/g, "") + "T" + h.replace(":", "") + "00";
  const br = salon.branches.find((b) => b.id === a.branch_id) || {};
  return `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${encodeURIComponent(`${a.service_name} - ${salon.name}`)}&dates=${f(a.date, a.time)}/${f(a.date, a.end_time)}&ctz=America/Guatemala&location=${encodeURIComponent(br.address || br.name || "")}&details=${encodeURIComponent(`Con ${a.stylist_name}. Tel. ${br.phone || salon.phone || ""}`)}`;
};

function PolicyBox({ quote, cur }) {
  const ru = quote?.rules;
  if (!ru) return null;
  return (
    <div className="space-y-1 rounded-xl bg-secondary/60 p-3 text-xs" data-testid="portal-policy">
      {ru.cancel_enabled && <div data-testid="portal-cancel-policy">{ru.policy_text}</div>}
      {quote.blocked && <div className="font-medium text-rose-700" data-testid="portal-blocked">No es posible reservar en línea con este número. Comuníquese con el salón.</div>}
      {ru.deposit_enabled && quote.deposit > 0 && <div className="font-medium text-amber-900" data-testid="portal-deposit-info">Esta reserva requiere un anticipo de {money(quote.deposit, cur)}, a enviar dentro de {ru.deposit_hours} horas o la cita se libera. {ru.bank_text} {ru.refund_text}</div>}
      {!ru.cancel_enabled && !(ru.deposit_enabled && quote.deposit > 0) && <div>Reserva sin anticipo.</div>}
    </div>
  );
}

function Steps({ step }) {
  return (
    <div className="sticky top-14 z-40 -mx-6 mb-6 flex gap-2 bg-[#FAF7F2]/90 px-6 py-2 backdrop-blur lg:static lg:mx-0 lg:px-0" data-testid="portal-steps">
      {["Servicios", "Horario", "Sus datos"].map((s, i) => (
        <div key={s} className={`flex flex-1 items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium ${step >= i + 1 ? "bg-primary text-white" : "bg-white text-slate-500"}`}><span>{i + 1}</span>{s}</div>
      ))}
    </div>
  );
}

function Success({ done, salon, slug, reset }) {
  const pend = done.deposit_total > 0;
  return (
    <section className="rounded-3xl border bg-white p-8 text-center lg:col-span-2" data-testid="booking-success">
      {pend ? <Clock className="mx-auto h-12 w-12 text-amber-600" /> : <CheckCircle2 className="mx-auto h-12 w-12 text-emerald-600" />}
      <h2 className="mt-3 font-heading text-2xl font-bold" data-testid="success-title">{pend ? "Reserva pendiente de anticipo" : "¡Reserva registrada!"}</h2>
      {pend && <p className="mx-auto mt-2 max-w-md text-sm font-semibold text-amber-900" data-testid="success-deposit-deadline">Envíe {money(done.deposit_total, salon.currency)} dentro de {done.rules?.deposit_hours} horas para asegurar su cita; si no, se libera automáticamente.</p>}
      <ul className="mx-auto mt-4 max-w-md space-y-3 text-left text-sm">
        {done.appointments.map((a) => (
          <li key={a.id} className="rounded-xl border p-3" data-testid="success-line">
            <b>{a.service_name}{a.addon_names.length ? ` + ${a.addon_names.join(", ")}` : ""}</b> · {a.date} de {a.time} a {a.end_time} con {a.stylist_name} ({a.branch_name})
            <div className="mt-2 flex gap-3 text-xs"><a href={gcal(a, salon)} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-primary underline" data-testid="gcal-link"><CalendarPlus className="h-3.5 w-3.5" />Google Calendar</a>
              <a href={`${API}/public/salon/${slug}/ics/${a.id}?t=${a.review_token}`} className="flex items-center gap-1 text-primary underline" data-testid="ics-link"><Download className="h-3.5 w-3.5" />Archivo .ics</a></div>
          </li>
        ))}
      </ul>
      {done.deposit_total > 0 && <p className="mx-auto mt-4 max-w-md rounded-xl bg-amber-50 p-3 text-sm" data-testid="success-deposit">Anticipo pendiente: <b>{money(done.deposit_total, salon.currency)}</b>. {done.rules?.bank_text} Si no lo recibimos en {done.rules?.deposit_hours} horas, la cita se libera.</p>}
      <p className="mt-3 text-sm text-muted-foreground">Le enviamos la confirmación por WhatsApp.</p>
      <Button className="mt-6 rounded-full" onClick={reset}>Reservar otra cita</Button>
    </section>
  );
}

export default function Portal() {
  const { slug } = useParams();
  const [salon, setSalon] = useState(null);
  const [error, setError] = useState("");
  const [lines, setLines] = useState([]);
  const [f, setF] = useState({ date: todayStr(), addon_ids: [], code: "+502" });
  const [data, setData] = useState(null);
  const [pick, setPick] = useState(null);
  const [done, setDone] = useState(null);
  const [fav, setFav] = useState(null);
  const [busy, setBusy] = useState(false);
  const [quote, setQuote] = useState(null);
  useEffect(() => {
    api.get(`/public/salon/${slug}`).then((r) => { setSalon(r.data); document.title = `${r.data.name} · Reservas`; setF((x) => ({ ...x, branch_id: r.data.branches[0]?.id })); }).catch((e) => setError(errMsg(e)));
  }, [slug]);
  const linesKey = JSON.stringify(lines);
  useEffect(() => {
    setPick(null);
    if (!lines.length || !f.branch_id || !f.date) return setData(null);
    api.post(`/public/salon/${slug}/slots-multi`, { branch_id: f.branch_id, date: f.date, lines }).then((r) => setData(r.data));
  }, [slug, linesKey, f.branch_id, f.date]); // eslint-disable-line
  const phone = `${f.code}${(f.number || "").replace(/\D/g, "")}`;
  const phoneOk = /^\d{7,12}$/.test((f.number || "").replace(/\D/g, ""));
  useEffect(() => {
    if (!phoneOk) return setFav(null);
    const t = setTimeout(() => api.post(`/public/salon/${slug}/last-stylist`, { phone, service_id: lines[0]?.service_id }).then((r) => setFav(r.data)).catch(() => setFav(null)), 400);
    return () => clearTimeout(t);
  }, [phone, linesKey]); // eslint-disable-line
  useEffect(() => {
    if (!f.branch_id) return;
    const t = setTimeout(() => api.post(`/public/salon/${slug}/quote`, { branch_id: f.branch_id, service_ids: lines.map((l) => l.service_id), phone: phoneOk ? phone : "" }).then((r) => setQuote(r.data)).catch(() => {}), 300);
    return () => clearTimeout(t);
  }, [slug, f.branch_id, linesKey, phone, phoneOk]); // eslint-disable-line
  if (error) return <div className="grid min-h-screen place-items-center p-6 text-center" data-testid="portal-error"><div><div className="font-display text-3xl italic">Portal no disponible</div><p className="mt-2 text-muted-foreground">{error}</p></div></div>;
  if (!salon) return <Loader />;
  const cur = salon.currency;
  const svcOf = (id) => salon.services.find((s) => s.id === id);
  const toggle = (s) => setLines(lines.some((l) => l.service_id === s.id) ? lines.filter((l) => l.service_id !== s.id) : [...lines, { service_id: s.id, stylist_id: "" }]);
  const sugg = data?.suggestions || [];
  const addons = sugg.filter((s) => f.addon_ids.includes(s.service.id));
  const total = (pick?.total || lines.reduce((a, l) => a + svcOf(l.service_id).price, 0)) + addons.reduce((a, s) => a + s.service.price, 0);
  const step = !lines.length ? 1 : !pick ? 2 : 3;
  const repeat = (a) => { setLines([{ service_id: a.service_id, stylist_id: a.stylist_id }]); setF({ ...f, branch_id: a.branch_id }); document.getElementById("reservar")?.scrollIntoView({ behavior: "smooth" }); };
  const book = async () => {
    if (!phoneOk) return toast.error("Teléfono inválido: escriba solo el número, sin código de país");
    setBusy(true);
    try { const r = await api.post(`/public/salon/${slug}/book-multi`, { ...f, phone, plan: pick.plan }); setDone({ ...r.data, rules: quote?.rules }); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const waitlist = async () => {
    if (!phoneOk || !f.name) return toast.error("Ingrese nombre y teléfono en Sus datos");
    try { await api.post(`/public/salon/${slug}/waitlist`, { ...f, phone, service_id: lines[0].service_id }); toast.success("Le avisaremos por WhatsApp si se libera un espacio"); } catch (e) { toast.error(errMsg(e)); }
  };
  const branchStylists = salon.stylists.filter((s) => s.branch_id === f.branch_id);
  return (
    <div className="min-h-screen pb-20 lg:pb-0" data-testid="public-portal">
      <header className="fixed top-0 z-50 w-full border-b bg-[#FAF7F2]/85 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-6 py-3">
          {salon.logo_url && <img src={img(salon.logo_url)} alt="logo" className="h-8 w-8 rounded-full object-cover" />}
          <div className="font-display text-xl italic">{salon.name}</div>
          <nav className="ml-auto hidden gap-5 text-sm sm:flex"><a href="#reservar">Reservar</a><a href="#nosotros">Nosotros</a><a href="#mis-citas">Mis citas</a></nav>
          {salon.whatsapp_number && <a href={`https://wa.me/${salon.whatsapp_number.replace("+", "")}`} className="flex items-center gap-1 text-sm text-[#128C7E]" data-testid="portal-whatsapp-link"><MessageCircle className="h-4 w-4" />WhatsApp</a>}
        </div>
      </header>
      <section className="relative h-[48vh] min-h-[340px]">
        <img src={img(salon.photo_urls[0]) || HERO} alt={salon.name} className="absolute inset-0 h-full w-full object-cover" />
        <div className="absolute inset-0 bg-gradient-to-r from-slate-900/80 via-slate-900/40 to-transparent" />
        <div className="relative mx-auto flex h-full max-w-6xl flex-col justify-end px-6 pb-10 text-white">
          <h1 className="max-w-2xl text-4xl font-extrabold tracking-tight sm:text-5xl lg:text-6xl fade-up">{salon.name}</h1>
          <p className="mt-3 max-w-xl text-white/85 fade-up-2" data-testid="salon-description">{salon.description || salon.portal?.tagline || "Reserva tu cita en segundos"}</p>
          {salon.rating && <div className="mt-2 flex items-center gap-1 text-sm"><Star className="h-4 w-4 fill-amber-400 text-amber-400" />{salon.rating} ({salon.reviews_count} opiniones)</div>}
        </div>
      </section>
      <main id="reservar" className="mx-auto max-w-6xl px-6 py-10">
        {salon.services.length === 0 ? <p className="rounded-3xl border bg-white p-10 text-center" data-testid="no-services">Este salón aún no tiene servicios disponibles.</p> : done ? (
          <Success done={done} salon={salon} slug={slug} reset={() => { setDone(null); setLines([]); setPick(null); }} />
        ) : (<>
          <Steps step={step} />
          <div className="grid gap-8 lg:grid-cols-[1fr_380px]">
            <div className="space-y-8">
              <section>
                <h2 className="mb-1 font-heading text-xl font-bold">1. Elija uno o varios servicios</h2>
                <p className="mb-4 text-sm text-muted-foreground">Si elige varios, buscamos horarios seguidos.</p>
                <div className="grid gap-3 sm:grid-cols-2">
                  {salon.services.map((s) => {
                    const on = lines.some((l) => l.service_id === s.id);
                    return (
                      <button key={s.id} onClick={() => toggle(s)} data-testid={`portal-service-${s.id}`} className={`flex gap-3 rounded-2xl border bg-white p-3 text-left transition-all hover:-translate-y-0.5 ${on ? "border-primary ring-2 ring-primary/30" : ""}`}>
                        {s.photo_url && <img src={img(s.photo_url)} alt={s.name} className="h-16 w-16 rounded-xl object-cover" />}
                        <div className="flex-1">
                          <div className="flex justify-between gap-2"><span className="font-semibold">{s.name}</span><span className="whitespace-nowrap font-semibold text-primary">{s.price_from ? "Desde " : ""}{money(s.price, cur)}</span></div>
                          <div className="mt-0.5 flex items-center gap-1 text-xs text-muted-foreground"><Clock className="h-3 w-3" />{s.duration} min · {s.category}</div>
                          {(s.description || s.price_note) && <div className="mt-1 text-xs text-slate-600">{s.description}{s.price_note ? ` · ${s.price_note}` : ""}</div>}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </section>
              {lines.length > 0 && <section className="fade-up">
                <h2 className="mb-4 font-heading text-xl font-bold">2. Sucursal, estilista y horario</h2>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div><Label>Sucursal</Label><select className="field" value={f.branch_id} onChange={(e) => { setF({ ...f, branch_id: e.target.value }); setLines(lines.map((l) => ({ ...l, stylist_id: "" }))); }} data-testid="portal-branch-select">{salon.branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></div>
                  <div><Label>Fecha</Label><input type="date" min={todayStr()} className="field" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} data-testid="portal-date-input" /></div>
                </div>
                {fav?.eligible && fav.branch_id === f.branch_id && lines[0].stylist_id !== fav.stylist_id && (
                  <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-primary/30 bg-primary/5 p-4 text-sm" data-testid="portal-favorite-banner">
                    <span>¿Desea agendar nuevamente con <b>{fav.stylist_name}</b>, quien le atendió la última vez?</span>
                    <Button size="sm" className="rounded-full" onClick={() => setLines(lines.map((l, i) => (i === 0 ? { ...l, stylist_id: fav.stylist_id } : l)))} data-testid="portal-favorite-accept">Sí, con {fav.stylist_name.split(" ")[0]}</Button>
                  </div>
                )}
                <div className="mt-4 space-y-2" data-testid="portal-stylist-choice">
                  <Label>¿Tiene un estilista de preferencia?</Label>
                  {lines.map((l, i) => (
                    <div key={l.service_id} className="flex flex-wrap items-center gap-2 text-sm">
                      <span className="w-40 truncate font-medium">{i + 1}. {svcOf(l.service_id).name}</span>
                      <select className="field max-w-xs" value={l.stylist_id} onChange={(e) => setLines(lines.map((x, j) => (j === i ? { ...x, stylist_id: e.target.value } : x)))} data-testid={`portal-stylist-select-${i}`}>
                        <option value="">Asígnenme según disponibilidad</option>
                        {branchStylists.map((s) => <option key={s.id} value={s.id}>{s.name}{s.specialties ? ` · ${s.specialties}` : ""}</option>)}
                      </select>
                    </div>
                  ))}
                </div>
                <div className="mt-5">
                  {!data ? <Loader /> : data.options.length > 0 ? (
                    <div className="flex flex-wrap gap-2">{data.options.map((o) => (
                      <button key={o.time} onClick={() => setPick(o)} data-testid={`portal-slot-${o.time}`} className={`rounded-full border px-4 py-1.5 text-sm transition-colors ${pick?.time === o.time ? "border-primary bg-primary text-white" : "bg-white hover:border-primary"}`}>{o.time}{lines.length > 1 ? `–${o.end_time}` : ""}</button>
                    ))}</div>
                  ) : <>
                    <p className="mb-2 text-sm font-medium" data-testid="no-slots-msg">{data.today ? "Hoy ya no hay turnos, estos son los próximos:" : "No hay horarios ese día. Estas son las alternativas:"}</p>
                    <Alternatives alts={data.alternatives} title={null} onPick={(s) => { setF({ ...f, date: s.date || f.date, branch_id: s.branch_id || f.branch_id }); }} />
                    {salon.waitlist && <Button variant="outline" className="mt-3" onClick={waitlist} data-testid="portal-waitlist-btn">Unirme a la lista de espera</Button>}
                  </>}
                  {pick && <ul className="mt-3 space-y-1 text-sm text-slate-600" data-testid="portal-plan">{pick.plan.map((p) => <li key={p.service_id}>{p.time}–{p.end_time} · {p.service_name} con <b>{p.stylist_name}</b></li>)}</ul>}
                </div>
              </section>}
              {sugg.length > 0 && pick && <section className="rounded-2xl border border-primary/30 bg-primary/5 p-5" data-testid="portal-suggestions">
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
            <aside className="h-fit space-y-3 rounded-3xl border bg-white p-6 lg:sticky lg:top-20" data-testid="portal-summary">
              <h2 className="font-heading text-xl font-bold">3. Sus datos</h2>
              <div><Label>Nombre completo</Label><input className="field" value={f.name || ""} onChange={(e) => setF({ ...f, name: e.target.value })} data-testid="portal-name-input" /></div>
              <div><Label>Teléfono WhatsApp</Label><div className="flex gap-2">
                <select className="field w-24" value={f.code} onChange={(e) => setF({ ...f, code: e.target.value })} data-testid="portal-country-select">{CODES.map((c) => <option key={c}>{c}</option>)}</select>
                <input className="field" inputMode="tel" placeholder="5555 5555" value={f.number || ""} onChange={(e) => setF({ ...f, number: e.target.value })} data-testid="portal-phone-input" /></div>
                {f.number && !phoneOk && <p className="mt-1 text-xs text-rose-600" data-testid="phone-error">Número inválido: escriba de 7 a 12 dígitos, sin el código de país.</p>}
                <p className="mt-1 text-xs text-muted-foreground">Si ya nos visitó, le sugeriremos a su estilista.</p></div>
              <div><Label>Correo (opcional)</Label><input className="field" value={f.email || ""} onChange={(e) => setF({ ...f, email: e.target.value })} data-testid="portal-email-input" />
                {!f.email && <p className="mt-1 text-xs text-muted-foreground">Sin correo, recibirá los avisos solo por WhatsApp.</p>}</div>
              <div><Label>¿Quién le recomendó? (opcional)</Label><input className="field" placeholder="Teléfono de quien le refirió" value={f.referred_by || ""} onChange={(e) => setF({ ...f, referred_by: e.target.value })} data-testid="portal-referred_by-input" />
                <p className="mt-1 text-xs text-muted-foreground">La persona que le recomendó recibe puntos de regalo en nuestro programa de fidelización.</p></div>
              <div className="space-y-1 border-t pt-3 text-sm">
                {lines.map((l) => <div key={l.service_id}>{svcOf(l.service_id).name}</div>)}
                {pick && <div className="text-muted-foreground">{f.date} · {pick.time}–{pick.end_time}</div>}
                <div className="text-lg font-bold" data-testid="portal-total">{money(total, cur)}</div>
              </div>
              <PolicyBox quote={quote} cur={cur} />
              <Button className="w-full rounded-full" disabled={busy || !pick || !f.name || !phoneOk || quote?.blocked} onClick={book} data-testid="portal-book-btn">{busy ? "Reservando..." : "Confirmar reserva"}</Button>
              <p className="text-center text-xs text-muted-foreground">Al confirmar acepta los <a href="#terminos" onClick={(e) => { e.preventDefault(); document.querySelector("[data-testid=footer-terms]")?.click(); }} className="underline" data-testid="portal-terms-link">términos y la política de privacidad</a>.</p>
            </aside>
          </div>
          <div className="fixed inset-x-0 bottom-0 z-40 flex items-center justify-between border-t bg-white px-6 py-3 lg:hidden" data-testid="mobile-summary-bar">
            <span className="text-sm font-semibold">{money(total, cur)}{pick ? ` · ${pick.time}` : ""}</span>
            <Button size="sm" className="rounded-full" disabled={busy || !pick || !f.name || !phoneOk || quote?.blocked} onClick={book}>Confirmar</Button>
          </div>
        </>)}
        <div className="mt-12 space-y-12"><SalonInfo salon={salon} /><MyAccount slug={slug} onRepeat={repeat} /></div>
      </main>
      <Footer salon={salon} />
    </div>
  );
}
