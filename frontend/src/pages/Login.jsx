import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/context/Auth";
import { errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";

const HERO = "https://images.unsplash.com/photo-1600948836101-f9ffda59d250?crop=entropy&cs=srgb&fm=jpg&q=85&w=1400";

export default function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const u = await login(email, password);
      nav(u.role === "super_admin" ? "/admin" : u.role === "stylist" ? "/app/agenda" : "/app");
    } catch (err) {
      toast.error(errMsg(err));
    } finally { setBusy(false); }
  };
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="relative hidden lg:block">
        <img src={HERO} alt="Salón de belleza" className="absolute inset-0 h-full w-full object-cover" />
        <div className="absolute inset-0 bg-gradient-to-t from-slate-900/80 to-transparent" />
        <div className="absolute bottom-12 left-12 max-w-md text-white">
          <div className="font-display text-5xl italic">SalonFlow</div>
          <p className="mt-3 text-lg text-white/85">Citas por WhatsApp, agenda inteligente y crecimiento para salones de belleza.</p>
        </div>
      </div>
      <div className="flex items-center justify-center p-6">
        <form onSubmit={submit} className="w-full max-w-sm space-y-5 fade-up" data-testid="login-form">
          <div>
            <h1 className="text-4xl font-extrabold tracking-tight">Bienvenido</h1>
            <p className="mt-1 text-sm text-muted-foreground">Ingrese a su panel de administración</p>
          </div>
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">Correo</label>
            <input className="field" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} data-testid="login-email-input" />
          </div>
          <div>
            <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">Contraseña</label>
            <input className="field" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} data-testid="login-password-input" />
          </div>
          <Button type="submit" className="w-full rounded-full" disabled={busy} data-testid="login-submit-button">{busy ? "Ingresando..." : "Ingresar"}</Button>
          <p className="text-center text-sm text-muted-foreground">
            ¿Tiene un salón? <Link to="/signup" className="font-medium text-primary underline" data-testid="signup-link">Registre su empresa</Link>
          </p>
        </form>
      </div>
    </div>
  );
}
