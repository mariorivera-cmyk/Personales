import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/context/Auth";
import { errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { CitaloLogo, CitaloSymbol } from "@/components/Brand";

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
      <div className="relative hidden overflow-hidden bg-[#2E1A47] p-14 text-[#FFF7E6] lg:flex lg:flex-col lg:justify-between grain" data-testid="login-brand-panel">
        <CitaloLogo light size="text-4xl" symbol="h-14 w-14" tagline testid="login-logo" />
        <div className="max-w-md fade-up">
          <div className="text-xs font-bold uppercase tracking-[0.2em] text-[#FFB020]">Valor central</div>
          <p className="mt-3 text-4xl font-extrabold leading-tight tracking-tight">Que cada cita se cumpla.</p>
          <p className="mt-4 text-lg text-[#FFF7E6]/80">Del chat a la silla, confirmado. Agenda, recordatorios y clientes de su salón, barbería o clínica en un solo lugar.</p>
        </div>
        <CitaloSymbol className="pointer-events-none absolute -bottom-16 -right-16 h-80 w-80 opacity-10" />
      </div>
      <div className="flex items-center justify-center p-6">
        <form onSubmit={submit} className="w-full max-w-sm space-y-5 fade-up" data-testid="login-form">
          <div className="lg:hidden"><CitaloLogo tagline testid="login-logo-mobile" /></div>
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
