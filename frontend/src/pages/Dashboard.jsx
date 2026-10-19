import { useEffect, useState } from "react";
import { toast } from "sonner";
import { CalendarCheck, CalendarClock, Gauge, Hourglass, DollarSign, Receipt, UserPlus, Repeat, Megaphone, TrendingUp, ArrowUpRight, Bell } from "lucide-react";
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";
import { api, money, errMsg } from "@/lib/api";
import { PageHeader, Kpi, Panel, StatusBadge, EmptyState, Loader } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Onboarding, Alerts, PendingSteps } from "@/components/Onboarding";
import { useAuth } from "@/context/Auth";

export default function Dashboard() {
  const { company, setup } = useAuth();
  if (company && !company.setup_complete && !setup?.setup_complete) {
    if (!setup) return null;
    if (!setup.skipped) return <SetupHome />;
  }
  return <Main />;
}

function SetupHome() {
  return (
    <div data-testid="setup-home">
      <PageHeader title="Configuremos su salón" subtitle="Termine la guía de arranque para activar la agenda, el portal de reservas y todos los módulos" />
      <Onboarding />
    </div>
  );
}

function Main() {
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/dashboard").then((r) => setD(r.data)).catch((e) => toast.error(errMsg(e))); }, []);
  const runReminders = async () => {
    const r = await api.post("/reminders/run");
    toast.success(`${r.data.sent} recordatorio(s) enviados por WhatsApp`);
  };
  if (!d) return <Loader />;
  const cur = d.currency;
  return (
    <div data-testid="dashboard-page">
      <PageHeader title="Dashboard gerencial" subtitle="Indicadores en tiempo real de operación, comercial y marketing"
        action={<Button variant="outline" onClick={runReminders} data-testid="run-reminders-btn"><Bell className="mr-1 h-4 w-4" />Enviar recordatorios</Button>} />
      <PendingSteps />
      <Onboarding />
      <Alerts />
      <h4 className="mb-3 text-xs font-semibold uppercase tracking-widest text-slate-500">Operación</h4>
      <div className="mb-8 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi label="Citas hoy" value={d.today} icon={CalendarCheck} testid="kpi-today" />
        <Kpi label="Citas futuras" value={d.future} icon={CalendarClock} testid="kpi-future" />
        <Kpi label="Ocupación hoy" value={`${d.occupancy}%`} icon={Gauge} testid="kpi-occupancy" />
        <Kpi label="Horas disponibles" value={d.available_hours} icon={Hourglass} testid="kpi-available" />
      </div>
      <h4 className="mb-3 text-xs font-semibold uppercase tracking-widest text-slate-500">Comercial (mes)</h4>
      <div className="mb-8 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi label="Ventas" value={money(d.sales, cur)} icon={DollarSign} testid="kpi-sales" accent="text-emerald-600" />
        <Kpi label="Ticket promedio" value={money(d.avg_ticket, cur)} icon={Receipt} testid="kpi-ticket" accent="text-emerald-600" />
        <Kpi label="Clientes nuevos" value={d.new_clients} icon={UserPlus} testid="kpi-new-clients" accent="text-emerald-600" />
        <Kpi label="Clientes recurrentes" value={d.recurring_clients} icon={Repeat} testid="kpi-recurring" accent="text-emerald-600" />
      </div>
      <h4 className="mb-3 text-xs font-semibold uppercase tracking-widest text-slate-500">Marketing</h4>
      <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Kpi label="Conversión campañas" value={`${d.campaign_conv}%`} icon={Megaphone} testid="kpi-campaign-conv" accent="text-rose-600" />
        <Kpi label="Conversión cross-selling" value={`${d.cross_conv}%`} icon={TrendingUp} testid="kpi-cross-conv" accent="text-rose-600" />
        <Kpi label="Conversión upselling" value={`${d.up_conv}%`} icon={ArrowUpRight} testid="kpi-up-conv" accent="text-rose-600" />
      </div>
      <div className="grid gap-6 lg:grid-cols-5">
        <Panel title="Ventas últimos 14 días" className="lg:col-span-3" testid="sales-chart">
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 1, height: 1 }}>
              <AreaChart data={d.series}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                <XAxis dataKey="date" fontSize={11} />
                <YAxis fontSize={11} />
                <Tooltip />
                <Area type="monotone" dataKey="ventas" stroke="#C2410C" fill="#C2410C33" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Panel>
        <Panel title="Agenda de hoy" className="lg:col-span-2" testid="today-list">
          {d.today_list.length === 0 ? <EmptyState text="Sin citas hoy" /> : (
            <ul className="max-h-64 space-y-2 overflow-auto">
              {d.today_list.map((a) => (
                <li key={a.id} className="flex items-center justify-between rounded-lg border p-3 text-sm">
                  <div><div className="font-medium">{a.time} · {a.client_name}</div><div className="text-xs text-muted-foreground">{a.service_name} · {a.stylist_name}</div></div>
                  <StatusBadge status={a.status} />
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}
