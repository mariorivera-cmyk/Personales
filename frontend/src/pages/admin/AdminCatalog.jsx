import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg, money } from "@/lib/api";
import { PageHeader, Panel } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import CrudPage, { FieldInput } from "@/components/CrudPage";

const SETTINGS = [
  { key: "currency", label: "Moneda", type: "select", options: [{ value: "GTQ", label: "GTQ" }, { value: "USD", label: "USD" }] },
  { key: "tax_rate", label: "Impuesto (%)", type: "number" }, { key: "annual_discount", label: "Descuento anual (%)", type: "number" },
  { key: "trial_days", label: "Días de prueba", type: "number" }, { key: "grace_days", label: "Periodo de gracia (días)", type: "number" },
  { key: "retry_days", label: "Reintentos de cobro (días)", type: "list", numeric: true }, { key: "extra_branch_price", label: "Sucursal adicional", type: "number" },
  { key: "extra_stylist_price", label: "Estilista adicional", type: "number" }, { key: "wa_pack_price", label: "Paquete WhatsApp (precio)", type: "number" },
  { key: "wa_pack_size", label: "Paquete WhatsApp (mensajes)", type: "number" }, { key: "wa_cost_per_message", label: "Costo por mensaje WhatsApp", type: "number" },
  { key: "wa_excess_price", label: "Precio mensaje excedente", type: "number" },
];

function Settings() {
  const [s, setS] = useState(null);
  useEffect(() => { api.get("/admin/settings").then((r) => setS(r.data)); }, []);
  if (!s) return null;
  const save = async () => { try { await api.put("/admin/settings", s); toast.success("Configuración guardada"); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <Panel testid="platform-settings">
      <div className="grid gap-4 sm:grid-cols-3">
        {SETTINGS.map((f) => (
          <div key={f.key}><label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">{f.label}</label>
            <FieldInput field={f} value={s[f.key]} onChange={(v) => setS({ ...s, [f.key]: v })} /></div>
        ))}
      </div>
      <Button className="mt-5" onClick={save} data-testid="platform-settings-save">Guardar</Button>
    </Panel>
  );
}

export default function AdminCatalog() {
  return (
    <div data-testid="admin-catalog-page">
      <PageHeader title="Planes, módulos y precios" subtitle="Configuración comercial de la plataforma" />
      <Tabs defaultValue="plans">
        <TabsList className="mb-6"><TabsTrigger value="plans" data-testid="tab-plans">Planes</TabsTrigger><TabsTrigger value="modules" data-testid="tab-modules">Módulos</TabsTrigger>
          <TabsTrigger value="coupons" data-testid="tab-coupons">Cupones</TabsTrigger><TabsTrigger value="settings" data-testid="tab-settings">Cobro y morosidad</TabsTrigger></TabsList>
        <TabsContent value="plans">
          <CrudPage embedded endpoint="/admin/plans" testid="plans" defaults={{ active: true, included_modules: ["agenda", "crm"], max_branches: 1, max_stylists: 3 }}
            fields={[
              { key: "name", label: "Nombre" }, { key: "price_monthly", label: "Precio mensual", type: "number" },
              { key: "max_branches", label: "Sucursales incluidas", type: "number" }, { key: "max_stylists", label: "Estilistas incluidos", type: "number" },
              { key: "wa_messages", label: "Mensajes WhatsApp incluidos", type: "number" }, { key: "active", label: "Activo", type: "switch" },
              { key: "included_modules", label: "Módulos incluidos", type: "multi", source: "/admin/modules", valueKey: "key" },
            ]}
            columns={[{ key: "name", label: "Plan" }, { key: "price_monthly", label: "Mensual", render: (r) => money(r.price_monthly) }, { key: "included_modules", label: "Módulos", render: (r) => r.included_modules?.length },
              { key: "limits", label: "Límites", render: (r) => `${r.max_branches} suc · ${r.max_stylists} est · ${r.wa_messages} msgs` }]} />
        </TabsContent>
        <TabsContent value="modules">
          <CrudPage embedded endpoint="/admin/modules" testid="modules"
            fields={[{ key: "key", label: "Clave interna" }, { key: "name", label: "Nombre" }, { key: "price_monthly", label: "Precio mensual", type: "number" }]}
            columns={[{ key: "name", label: "Módulo" }, { key: "key", label: "Clave" }, { key: "price_monthly", label: "Precio", render: (r) => money(r.price_monthly) }]} />
        </TabsContent>
        <TabsContent value="coupons">
          <CrudPage embedded endpoint="/admin/coupons" testid="platform-coupons"
            fields={[{ key: "code", label: "Código (mayúsculas)" }, { key: "percent", label: "% descuento", type: "number" }, { key: "description", label: "Descripción", full: true }]}
            columns={[{ key: "code", label: "Código" }, { key: "percent", label: "%" }, { key: "description", label: "Descripción" }]} />
        </TabsContent>
        <TabsContent value="settings"><Settings /></TabsContent>
      </Tabs>
    </div>
  );
}
