import { NavLink, Outlet, Navigate, useNavigate, useLocation } from "react-router-dom";
import { useState } from "react";
import {
  LayoutDashboard, CalendarDays, Users, MessageCircle, ListOrdered, Scissors, Building2, UserRound, Ban, Gift,
  TrendingUp, Megaphone, BarChart3, Settings, CreditCard, LogOut, Shield, Package, Wallet, Menu, X, AlertTriangle, ExternalLink, Banknote, Percent, Boxes, Star,
} from "lucide-react";
import { useAuth } from "@/context/Auth";
import { ROLES, CO_STATUS } from "@/lib/api";

const S = ["company_admin", "branch_manager", "receptionist"];
const ALL = [...S, "stylist"];
const M = ["company_admin", "branch_manager"];
const A = ["company_admin"];
const COMPANY_NAV = [
  { to: "/app", label: "Dashboard", icon: LayoutDashboard, roles: S, end: true },
  { to: "/app/agenda", label: "Agenda", icon: CalendarDays, roles: ALL },
  { to: "/app/clientes", label: "Clientes (CRM)", icon: Users, roles: ALL },
  { to: "/app/caja", label: "Caja", icon: Banknote, roles: S },
  { to: "/app/comisiones", label: "Comisiones", icon: Percent, roles: M },
  { to: "/app/inventario", label: "Inventario", icon: Boxes, roles: S },
  { to: "/app/resenas", label: "Reseñas y galería", icon: Star, roles: S },
  { to: "/app/whatsapp", label: "WhatsApp", icon: MessageCircle, roles: ALL, mod: "whatsapp" },
  { to: "/app/espera", label: "Lista de espera", icon: ListOrdered, roles: S, mod: "waitlist" },
  { to: "/app/sucursales", label: "Sucursales", icon: Building2, roles: A },
  { to: "/app/servicios", label: "Servicios", icon: Scissors, roles: A },
  { to: "/app/estilistas", label: "Estilistas", icon: UserRound, roles: M },
  { to: "/app/bloqueos", label: "Bloqueos y vacaciones", icon: Ban, roles: M },
  { to: "/app/fidelizacion", label: "Fidelización", icon: Gift, roles: S, mod: "loyalty" },
  { to: "/app/paquetes", label: "Paquetes", icon: Package, roles: S },
  { to: "/app/ventas", label: "Cross / Upselling", icon: TrendingUp, roles: A, mod: "upsell" },
  { to: "/app/marketing", label: "Marketing", icon: Megaphone, roles: A, mod: "marketing" },
  { to: "/app/reportes", label: "Reportes", icon: BarChart3, roles: M, mod: "reports_adv" },
  { to: "/app/config", label: "Configuración", icon: Settings, roles: A },
  { to: "/app/facturacion", label: "Mi suscripción", icon: CreditCard, roles: A },
];
const STEP_PATHS = { services: ["/app/servicios"], stylists: ["/app/estilistas"], description: ["/app/config"], address: ["/app/sucursales"], rules: ["/app/config"], bank: ["/app/config"] };
const STEP_ORDER = ["services", "stylists", "description", "address", "rules", "bank"];
const setupPaths = (current) => ["/app", ...STEP_ORDER.slice(0, STEP_ORDER.indexOf(current) + 1).flatMap((k) => STEP_PATHS[k])];
const ADMIN_NAV = [
  { to: "/admin", label: "Resumen SaaS", icon: Shield, end: true },
  { to: "/admin/empresas", label: "Empresas", icon: Building2 },
  { to: "/admin/catalogo", label: "Planes y módulos", icon: Package },
  { to: "/admin/pagos", label: "Pagos", icon: Wallet },
];

function Item({ n, onClick }) {
  return (
    <NavLink to={n.to} end={n.end} onClick={onClick} data-testid={`nav-${n.to.replace(/\//g, "-").slice(1)}`}
      className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${isActive ? "bg-primary text-white" : "text-slate-300 hover:bg-white/10 hover:text-white"}`}>
      <n.icon className="h-4 w-4" />{n.label}
    </NavLink>
  );
}

export default function Layout() {
  const { user, company, logout, enterCompany, setup: setupInfo } = useAuth();
  const [open, setOpen] = useState(false);
  const nav = useNavigate();
  const loc = useLocation();
  if (user === null) return <div className="grid h-screen place-items-center text-muted-foreground">Cargando...</div>;
  if (!user) return <Navigate to="/login" replace />;
  const isSA = user.role === "super_admin";
  const pendingSkip = !!company && !company.setup_complete && !isSA && setupInfo?.skipped && !setupInfo?.setup_complete;
  const setup = !!company && !company.setup_complete && !isSA && !setupInfo?.setup_complete && !setupInfo?.skipped;
  const SETUP_PATHS = setupPaths(setupInfo?.current);
  if (setup && setupInfo && loc.pathname.startsWith("/app") && !SETUP_PATHS.includes(loc.pathname)) return <Navigate to="/app" replace />;
  const items = COMPANY_NAV.filter((n) => (isSA || n.roles.includes(user.role)) && (!n.mod || (company?.enabled_modules || []).includes(n.mod)) && (!setup || SETUP_PATHS.includes(n.to)));
  const locked = company && ["past_due", "suspended_partial", "suspended"].includes(company.status);
  const sidebar = (
    <aside className="flex h-full w-64 flex-col bg-slate-900 p-4 text-white grain">
      <div className="mb-6 px-2">
        <div className="font-display text-2xl italic">SalonFlow</div>
        <div className="text-xs text-slate-400">{ROLES[user.role]}</div>
      </div>
      <nav className="flex-1 space-y-1 overflow-y-auto">
        {isSA && <>
          <div className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-widest text-slate-500">Plataforma</div>
          {ADMIN_NAV.map((n) => <Item key={n.to} n={n} onClick={() => setOpen(false)} />)}
        </>}
        {company && <>
          <div className="px-3 pb-1 pt-4 text-[10px] font-semibold uppercase tracking-widest text-slate-500">{company.name}</div>
          {items.map((n) => <Item key={n.to} n={n} onClick={() => setOpen(false)} />)}
          {setup && <p className="mx-3 mt-4 rounded-lg bg-white/5 p-3 text-xs leading-relaxed text-slate-400" data-testid="setup-nav-note">Cada opción aparece al completar el paso anterior de la guía de arranque.</p>}
          {pendingSkip && <NavLink to="/app" onClick={() => setOpen(false)} className="mx-3 mt-4 flex items-center gap-2 rounded-lg bg-amber-400/15 p-3 text-xs font-semibold text-amber-200 hover:bg-amber-400/25" data-testid="setup-pending-indicator">{setupInfo.pending.length === 1 ? "Falta 1 paso" : `Faltan ${setupInfo.pending.length} pasos`} para dejar su salón listo →</NavLink>}
        </>}
      </nav>
      <div className="border-t border-white/10 pt-3">
        <div className="truncate px-2 text-sm">{user.name}</div>
        <div className="truncate px-2 text-xs text-slate-400">{user.email}</div>
        <button className="mt-2 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-slate-300 hover:bg-white/10" onClick={() => { logout(); nav("/login"); }} data-testid="logout-btn">
          <LogOut className="h-4 w-4" />Cerrar sesión
        </button>
      </div>
    </aside>
  );
  return (
    <div className="flex min-h-screen">
      <div className="sticky top-0 hidden h-screen lg:block">{sidebar}</div>
      {open && <div className="fixed inset-0 z-50 flex lg:hidden"><div className="h-full">{sidebar}</div><div className="flex-1 bg-black/40" onClick={() => setOpen(false)} /></div>}
      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-40 flex items-center gap-3 border-b bg-[#FAF7F2]/80 px-4 py-3 backdrop-blur-md sm:px-8">
          <button className="lg:hidden" onClick={() => setOpen(!open)} data-testid="mobile-menu-btn">{open ? <X /> : <Menu />}</button>
          {isSA && company && (
            <div className="flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-sm text-primary" data-testid="company-context-banner">
              Viendo como: <b>{company.name}</b>
              <button className="underline" onClick={() => { enterCompany(null); nav("/admin/empresas"); }} data-testid="exit-company-btn">Salir</button>
            </div>
          )}
          {company?.slug && !setup && company.setup_complete && (
            <a href={`/b/${company.slug}`} target="_blank" rel="noreferrer" className="ml-auto flex items-center gap-1 text-sm text-slate-600 hover:text-primary" data-testid="portal-link">
              Portal de reservas <ExternalLink className="h-3.5 w-3.5" />
            </a>
          )}
        </header>
        {locked && (
          <div className="flex items-center gap-2 bg-amber-100 px-8 py-2 text-sm text-amber-900" data-testid="suspension-banner">
            <AlertTriangle className="h-4 w-4" /> Estado de cuenta: {CO_STATUS[company.status]}. {company.status !== "past_due" ? "Acceso de solo lectura." : "Regularice su pago para evitar la suspensión."}
          </div>
        )}
        <main className="mx-auto max-w-7xl px-4 py-8 sm:px-8 lg:py-10"><Outlet /></main>
      </div>
    </div>
  );
}
