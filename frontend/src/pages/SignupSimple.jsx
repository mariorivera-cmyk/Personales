import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { useAuth } from "@/context/Auth";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/Common";

export default function SignupSimple() {
  const nav = useNavigate();
  const { setToken } = useAuth();
  const [f, setF] = useState({});
  const [slug, setSlug] = useState(null);
  const [busy, setBusy] = useState(false);
  const want = f.slug || f.company_name || "";
  useEffect(() => {
    if (!want) return setSlug(null);
    const t = setTimeout(() => api.get("/public/slug-check", { params: { slug: want } }).then((r) => setSlug(r.data)), 350);
    return () => clearTimeout(t);
  }, [want]);
  const submit = async (e) => {
    e.preventDefault();
    if (slug && !slug.available) return toast.error("El enlace ya está en uso: elija una sugerencia");
    setBusy(true);
    try {
      const r = await api.post("/signup", { ...f, slug: f.slug?.trim() || slug?.slug });
      await setToken(r.data.token);
      toast.success("¡Bienvenida! Su prueba gratuita de 14 días comenzó.");
      nav("/app");
    } catch (err) { toast.error(errMsg(err)); } finally { setBusy(false); }
  };
  return (
    <div className="grid min-h-screen place-items-center px-4 py-10">
      <form onSubmit={submit} className="w-full max-w-md space-y-4 rounded-3xl border bg-white p-8 fade-up" data-testid="signup-form">
        <Link to="/login" className="font-display text-2xl italic text-primary">SalonFlow</Link>
        <h1 className="text-3xl font-extrabold tracking-tight">Pruebe gratis 14 días</h1>
        <p className="text-sm text-muted-foreground">Sin tarjeta. El NIT y el pago se piden al activar su plan.</p>
        {[["company_name", "Nombre del salón"], ["email", "Correo", "email"], ["password", "Contraseña (mín. 8)", "password"], ["whatsapp_number", "WhatsApp del salón (+502...)"]].map(([k, l, t]) => (
          <div key={k}><Label>{l}</Label><input className="field" type={t || "text"} required minLength={k === "password" ? 8 : undefined} value={f[k] || ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} data-testid={`signup-${k}-input`} /></div>
        ))}
        <div><Label>Enlace del portal (opcional)</Label><input className="field" placeholder={slug?.slug || "misalon"} value={f.slug || ""} onChange={(e) => setF({ ...f, slug: e.target.value })} data-testid="signup-slug-input" />
          {slug && <p className={`mt-1 text-xs ${slug.available ? "text-emerald-700" : "text-rose-600"}`} data-testid="slug-status">
            {slug.available ? `Disponible: /b/${slug.slug}` : <>Ya existe. Sugerencias: {slug.suggestions.map((s) => <button type="button" key={s} className="mr-2 underline" onClick={() => setF({ ...f, slug: s })}>{s}</button>)}</>}</p>}</div>
        <p className="text-xs text-muted-foreground">Al crear la cuenta acepta los términos del servicio y la política de datos.</p>
        <Button type="submit" className="w-full rounded-full" disabled={busy} data-testid="signup-submit-button">{busy ? "Creando..." : "Crear mi salón"}</Button>
      </form>
    </div>
  );
}
