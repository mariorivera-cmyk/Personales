import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Play, Sparkles } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { PageHeader, Panel, EmptyState } from "@/components/Common";
import { Button } from "@/components/ui/button";
import CrudPage from "@/components/CrudPage";

const TYPES = { birthday: "Cumpleaños", inactive: "Clientes inactivos", retouch: "Recordatorio de retoque", promo: "Promoción", recovery: "Recuperación de clientes" };

export default function Marketing() {
  const [recs, setRecs] = useState([]);
  useEffect(() => { api.get("/recommendations").then((r) => setRecs(r.data)).catch(() => {}); }, []);
  const run = async (row, reload) => {
    try { const r = await api.post(`/campaigns/${row.id}/run`); toast.success(`Campaña enviada a ${r.data.sent} cliente(s)`); reload(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div data-testid="marketing-page">
      <PageHeader title="Marketing automatizado" subtitle="Campañas por WhatsApp o correo y motor de recomendaciones" />
      <Panel title="Motor de recomendaciones" className="mb-8" testid="recommendations-panel"
        action={<span className="flex items-center gap-1 text-xs text-primary"><Sparkles className="h-3.5 w-3.5" />Basado en historial y frecuencia</span>}>
        {recs.length === 0 ? <EmptyState text="Sin recomendaciones pendientes" /> : (
          <ul className="grid gap-2 md:grid-cols-2">
            {recs.slice(0, 12).map((r) => (
              <li key={r.client_id + r.service_id} className="rounded-lg border p-3 text-sm" data-testid="recommendation-item">
                <div className="font-medium">{r.client_name} <span className="text-xs text-muted-foreground">{r.client_phone}</span></div>
                <div className="text-slate-600">{r.message}</div>
              </li>
            ))}
          </ul>
        )}
      </Panel>
      <CrudPage title="Campañas" endpoint="/campaigns" testid="campaigns" defaults={{ type: "promo", channel: "whatsapp", days: 60, active: true }}
        fields={[
          { key: "name", label: "Nombre" }, { key: "type", label: "Tipo", type: "select", options: Object.entries(TYPES).map(([value, label]) => ({ value, label })) },
          { key: "channel", label: "Canal", type: "select", options: [{ value: "whatsapp", label: "WhatsApp" }, { value: "email", label: "Correo electrónico" }] },
          { key: "days", label: "Días de inactividad", type: "number" },
          { key: "message", label: "Mensaje (usa {nombre} y {salon})", type: "textarea" },
        ]}
        columns={[
          { key: "name", label: "Campaña" }, { key: "type", label: "Tipo", render: (r) => TYPES[r.type] }, { key: "channel", label: "Canal" },
          { key: "sent_total", label: "Enviados", render: (r) => r.sent_total || 0 }, { key: "last_run", label: "Última ejecución", render: (r) => (r.last_run ? r.last_run.slice(0, 16).replace("T", " ") : "—") },
        ]}
        rowActions={(row, reload) => <Button size="sm" variant="outline" onClick={() => run(row, reload)} data-testid={`campaign-run-${row.id}`}><Play className="mr-1 h-3.5 w-3.5" />Ejecutar</Button>} />
    </div>
  );
}
