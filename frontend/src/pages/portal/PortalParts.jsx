import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg, money } from "@/lib/api";
import { Label } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { CancelDialog } from "@/components/Checkout";
import { RescheduleDialog } from "@/pages/portal/RescheduleDialog";
import { MapPin, Phone, Star, Instagram, Facebook } from "lucide-react";
import { DAYS } from "@/lib/api";

const B = process.env.REACT_APP_BACKEND_URL;
export const img = (u) => (u?.startsWith("/api") ? `${B}${u}` : u);
export const DEFAULT_TERMS = "Al reservar acepta la política de cancelación del salón. Sus datos (nombre, teléfono, correo e historial de citas) se usan únicamente para gestionar sus citas, enviarle recordatorios y beneficios del programa de fidelización. Puede solicitar la exportación o el borrado de sus datos desde \"Mis citas\".";

export function SalonInfo({ salon }) {
  const so = salon.social || {};
  return (
    <section id="nosotros" className="space-y-8" data-testid="salon-info">
      <div className="grid gap-6 md:grid-cols-2">
        {salon.branches.map((b) => (
          <div key={b.id} className="overflow-hidden rounded-3xl border bg-white" data-testid={`branch-info-${b.id}`}>
            {b.address && <iframe title={b.name} className="h-48 w-full" loading="lazy" src={`https://maps.google.com/maps?q=${encodeURIComponent(b.address)}&output=embed`} />}
            <div className="space-y-2 p-5 text-sm">
              <div className="font-heading text-lg font-bold">{b.name}</div>
              <div className="flex gap-2"><MapPin className="h-4 w-4 shrink-0 text-primary" />{b.address || "Dirección por confirmar"}</div>
              {(b.phone || salon.phone) && <div className="flex gap-2"><Phone className="h-4 w-4 text-primary" />{b.phone || salon.phone}</div>}
              <table className="w-full text-xs">{DAYS.map((d, i) => <tr key={d}><td className="py-0.5">{d}</td><td className="text-right">{b.hours?.[i] ? `${b.hours[i][0]} – ${b.hours[i][1]}` : "Cerrado"}</td></tr>)}</table>
            </div>
          </div>
        ))}
      </div>
      {(so.instagram || so.facebook || so.tiktok) && (
        <div className="flex gap-4 text-sm">{so.instagram && <a href={so.instagram} target="_blank" rel="noreferrer" className="flex items-center gap-1 hover:text-primary"><Instagram className="h-4 w-4" />Instagram</a>}
          {so.facebook && <a href={so.facebook} target="_blank" rel="noreferrer" className="flex items-center gap-1 hover:text-primary"><Facebook className="h-4 w-4" />Facebook</a>}
          {so.tiktok && <a href={so.tiktok} target="_blank" rel="noreferrer" className="hover:text-primary">TikTok</a>}</div>
      )}
      {salon.show_team !== false && salon.stylists.length > 0 && (
        <div data-testid="team-section"><h2 className="mb-4 font-heading text-2xl font-bold">Nuestro equipo</h2>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">{salon.stylists.map((s) => (
            <div key={s.id} className="rounded-2xl border bg-white p-4 text-center">
              {s.photo ? <img src={img(s.photo)} alt={s.name} className="mx-auto h-20 w-20 rounded-full object-cover" /> : <div className="mx-auto grid h-20 w-20 place-items-center rounded-full bg-primary/10 font-display text-2xl text-primary">{s.name[0]}</div>}
              <div className="mt-2 font-semibold">{s.name}</div><div className="text-xs text-muted-foreground">{s.specialties}</div>
            </div>
          ))}</div></div>
      )}
      {salon.gallery.length > 0 && (
        <div data-testid="gallery-section"><h2 className="mb-4 font-heading text-2xl font-bold">Nuestros trabajos</h2>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{salon.gallery.map((g) => <figure key={g.id}><img src={img(g.url)} alt={g.caption} className="aspect-square w-full rounded-2xl object-cover" /><figcaption className="mt-1 text-xs text-muted-foreground">{g.caption}</figcaption></figure>)}</div></div>
      )}
      {salon.reviews.length > 0 && (
        <div data-testid="reviews-section"><h2 className="mb-4 flex items-center gap-2 font-heading text-2xl font-bold"><Star className="h-5 w-5 fill-amber-400 text-amber-400" />{salon.rating} · {salon.reviews_count} opiniones</h2>
          <div className="grid gap-3 md:grid-cols-3">{salon.reviews.map((r, i) => <div key={i} className="rounded-2xl border bg-white p-4 text-sm"><div className="text-amber-500">{"★".repeat(r.rating)}{"☆".repeat(5 - r.rating)}</div><p className="mt-1">{r.comment || "—"}</p><div className="mt-2 text-xs text-muted-foreground">{r.client_name} · {r.service_name}</div></div>)}</div></div>
      )}
    </section>
  );
}

export function Footer({ salon }) {
  const [open, setOpen] = useState(null);
  const legal = salon.legal || {};
  const texts = { terms: ["Términos y condiciones", legal.terms || DEFAULT_TERMS], privacy: ["Política de privacidad", legal.privacy || DEFAULT_TERMS] };
  return (
    <footer className="mt-16 border-t bg-slate-900 py-8 text-sm text-slate-300" data-testid="portal-footer">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6">
        <span>© {new Date().getFullYear()} {salon.name}</span>
        <div className="flex gap-4">
          <button onClick={() => setOpen("terms")} className="hover:text-white" data-testid="footer-terms">Términos</button>
          <button onClick={() => setOpen("privacy")} className="hover:text-white" data-testid="footer-privacy">Privacidad</button>
          <a href={`https://wa.me/${(salon.whatsapp_number || "").replace("+", "")}`} className="hover:text-white" data-testid="footer-contact">Contacto</a>
        </div>
      </div>
      <Dialog open={!!open} onOpenChange={(o) => !o && setOpen(null)}>
        <DialogContent data-testid="legal-dialog"><DialogHeader><DialogTitle>{open && texts[open][0]}</DialogTitle></DialogHeader><p className="whitespace-pre-wrap text-sm">{open && texts[open][1]}</p></DialogContent>
      </Dialog>
    </footer>
  );
}

export function MyAccount({ slug, onRepeat }) {
  const key = `ctok_${slug}`;
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const [acc, setAcc] = useState(null);
  const [res] = useState({});
  const [cancel, setCancel] = useState(null);
  const [resched, setResched] = useState(null);
  const [preview, setPreview] = useState(null);
  const openCancel = (a) => api.get(`/public/salon/${slug}/appointments/${a.id}/cancel-preview`, hdr()).then((r) => { setPreview(r.data); setCancel(a); }).catch((e) => toast.error(errMsg(e)));
  const tok = () => { const t = JSON.parse(sessionStorage.getItem(key) || "null"); return t && t.exp > Date.now() ? t.token : null; };
  const hdr = () => ({ headers: { "X-Client-Token": tok() } });
  const load = () => api.get(`/public/salon/${slug}/account`, hdr()).then((r) => setAcc(r.data)).catch(() => { sessionStorage.removeItem(key); setAcc(null); });
  useEffect(() => { if (tok()) load(); }, []); // eslint-disable-line
  const request = async () => { try { const r = await api.post(`/public/salon/${slug}/otp`, { phone }); toast.success(r.data.message); setSent(true); } catch (e) { toast.error(errMsg(e)); } };
  const verify = async () => {
    try { const r = await api.post(`/public/salon/${slug}/otp/verify`, { phone, code }); sessionStorage.setItem(key, JSON.stringify({ token: r.data.token, exp: Date.now() + 29 * 60000 })); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  const manage = async (a, action, extra = {}) => {
    try { await api.post(`/public/salon/${slug}/appointments/${a.id}`, { action, ...(res[a.id] || {}), ...extra }, hdr()); toast.success(action === "cancel" ? "Su cita fue cancelada" : action === "confirm" ? "Cita confirmada" : "Cita reprogramada"); setCancel(null); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  const del = async () => { if (!window.confirm("¿Solicitar el borrado de sus datos personales?")) return; const r = await api.post(`/public/salon/${slug}/account/delete-request`, {}, hdr()); toast.success(r.data.message); };
  return (
    <section id="mis-citas" className="rounded-3xl border bg-white p-6" data-testid="my-appointments">
      <h2 className="font-heading text-xl font-bold">Mis citas</h2>
      {!acc ? (
        <div className="mt-3 max-w-md space-y-2">
          <p className="text-sm text-muted-foreground">Por seguridad le enviaremos un código de 6 dígitos por WhatsApp.</p>
          <div className="flex gap-2"><input className="field" placeholder="+502 5555 5555" value={phone} onChange={(e) => setPhone(e.target.value)} data-testid="my-phone-input" /><Button onClick={request} data-testid="my-find-btn">{sent ? "Reenviar" : "Enviar código"}</Button></div>
          {sent && <div className="flex gap-2"><input className="field" placeholder="Código" maxLength={6} value={code} onChange={(e) => setCode(e.target.value)} data-testid="otp-code-input" /><Button onClick={verify} data-testid="otp-verify-btn">Verificar</Button></div>}
        </div>
      ) : (
        <div className="mt-3 space-y-4 text-sm" data-testid="account-view">
          <div className="flex flex-wrap items-center gap-3"><b>{acc.name}</b><span className="rounded-full bg-primary/10 px-3 py-0.5 text-primary" data-testid="account-points">{acc.points} puntos</span>{acc.membership && <span className="rounded-full bg-amber-100 px-3 py-0.5">Membresía {acc.membership}</span>}
            <button className="ml-auto text-xs underline" onClick={del} data-testid="delete-data-btn">Solicitar borrado de mis datos</button></div>
          <h3 className="font-semibold">Próximas</h3>
          {acc.upcoming.length === 0 && <p className="text-muted-foreground">No hay citas próximas.</p>}
          {acc.upcoming.map((a) => (
            <div key={a.id} className="rounded-xl border p-3" data-testid={`my-appt-${a.id}`}>
              <div className="font-medium">{a.service_name} · {a.date} {a.time}–{a.end_time}</div><div className="text-muted-foreground">{a.stylist_name} · {a.branch_name}{a.deposit_status === "pending" ? ` · Anticipo pendiente ${money(a.deposit_required)}` : ""}</div>
              <div className="mt-2 flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={() => setResched(a)} data-testid={`my-resched-${a.id}`}>Reprogramar</Button>
                <Button size="sm" variant="outline" onClick={() => manage(a, "confirm")} data-testid={`my-confirm-${a.id}`}>Confirmar</Button>
                <Button size="sm" variant="destructive" onClick={() => openCancel(a)} data-testid={`my-cancel-${a.id}`}>Cancelar</Button>
              </div>
            </div>
          ))}
          <h3 className="font-semibold">Historial</h3>
          {acc.past.map((a) => (
            <div key={a.id} className="flex items-center justify-between rounded-xl border p-3"><span>{a.date} · {a.service_name} con {a.stylist_name}</span><Button size="sm" variant="outline" onClick={() => onRepeat(a)} data-testid={`repeat-${a.id}`}>Repetir</Button></div>
          ))}
        </div>
      )}
      <CancelDialog open={!!cancel} client preview={preview} onClose={() => setCancel(null)} onConfirm={(reason) => manage(cancel, "cancel", { reason })} />
      {resched && <RescheduleDialog slug={slug} appt={resched} hdr={hdr} onClose={() => setResched(null)} onDone={load} />}
    </section>
  );
}

export function useLegalLabel() { return <Label>.</Label>; }
