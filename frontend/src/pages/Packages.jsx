import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus } from "lucide-react";
import { api, errMsg, money } from "@/lib/api";
import { useAuth } from "@/context/Auth";
import { PageHeader, Kpi } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import CrudPage from "@/components/CrudPage";
import { SellPackageDialog, PkgBadge, PkgItems, PK_STATUS } from "@/components/PackageParts";

function Sold({ reload, owner }) {
  const [rows, setRows] = useState([]);
  const [status, setStatus] = useState("");
  const [n, setN] = useState(0);
  const load = () => setN((x) => x + 1);
  useEffect(() => {
    let live = true;
    api.get("/client-packages", { params: { status } }).then((r) => { if (live) setRows(r.data); }).catch((e) => toast.error(errMsg(e)));
    return () => { live = false; };
  }, [status, reload, n]);
  const voidIt = async (cp) => {
    const reason = window.prompt("Motivo de la anulación");
    if (!reason) return;
    try { await api.post(`/client-packages/${cp.id}/void`, { reason }); toast.success("Paquete anulado"); load(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div>
      <select className="field mb-3 w-48" value={status} onChange={(e) => setStatus(e.target.value)} data-testid="sold-status-filter">
        <option value="">Todos</option>{Object.entries(PK_STATUS).map(([k, [l]]) => <option key={k} value={k}>{l}</option>)}
      </select>
      <div className="overflow-x-auto rounded-2xl border bg-white">
        <table className="w-full text-sm" data-testid="sold-packages-table">
          <thead className="bg-secondary/60 text-left text-xs uppercase tracking-wider text-slate-500"><tr>{["Clienta", "Paquete", "Sesiones", "Vendido", "Vence", "Precio", "Estado", ""].map((h) => <th key={h} className="px-4 py-3">{h}</th>)}</tr></thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={8} className="px-4 py-6 text-center text-muted-foreground">Aún no hay paquetes vendidos.</td></tr>}
            {rows.map((cp) => (
              <tr key={cp.id} className="border-t" data-testid={`sold-row-${cp.id}`}>
                <td className="px-4 py-3">{cp.client_name}<div className="text-xs text-muted-foreground">{cp.client_phone}</div></td>
                <td className="px-4 py-3"><div className="font-medium">{cp.name}</div><PkgItems cp={cp} /></td>
                <td className="px-4 py-3">{cp.remaining} / {cp.total}</td><td className="px-4 py-3">{cp.sold_at}</td><td className="px-4 py-3">{cp.expires}</td>
                <td className="px-4 py-3">{money(cp.price)}</td><td className="px-4 py-3"><PkgBadge status={cp.status} testid={`sold-status-${cp.id}`} /></td>
                <td className="px-4 py-3 text-right">{owner && cp.status !== "voided" && cp.uses.length === 0 && <Button size="sm" variant="ghost" onClick={() => voidIt(cp)} data-testid={`sold-void-${cp.id}`}>Anular</Button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Packages() {
  const { user } = useAuth();
  const owner = ["company_admin", "super_admin"].includes(user?.role);
  const [rep, setRep] = useState(null);
  const [sell, setSell] = useState(false);
  const [tick, setTick] = useState(0);
  useEffect(() => { api.get("/client-packages/report").then((r) => setRep(r.data)).catch(() => {}); }, [tick]);
  return (
    <div data-testid="packages-page">
      <PageHeader title="Paquetes" subtitle="Sesiones prepagadas que se descuentan al cobrar la cita"
        action={<Button onClick={() => setSell(true)} data-testid="sell-package-btn"><Plus className="mr-1 h-4 w-4" />Vender paquete</Button>} />
      {rep && <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-5">
        <Kpi label="Vendidos" value={rep.sold} testid="pk-kpi-sold" /><Kpi label="Ingresos" value={money(rep.revenue)} testid="pk-kpi-revenue" />
        <Kpi label="Sesiones usadas" value={rep.used} testid="pk-kpi-used" /><Kpi label="Sesiones pendientes" value={rep.pending} hint={`${rep.active} paquetes vigentes`} testid="pk-kpi-pending" />
        <Kpi label="Vencidos" value={rep.expired} hint={`${rep.lost} sesiones sin usar`} testid="pk-kpi-expired" />
      </div>}
      <Tabs defaultValue="sold">
        <TabsList className="mb-4"><TabsTrigger value="sold" data-testid="tab-sold">Vendidos</TabsTrigger><TabsTrigger value="catalog" data-testid="tab-catalog">Catálogo</TabsTrigger></TabsList>
        <TabsContent value="sold"><Sold reload={tick} owner={owner} /></TabsContent>
        <TabsContent value="catalog">
          <CrudPage embedded endpoint="/packages" testid="packages" canWrite={owner} defaults={{ active: true, validity_days: 90, items: [] }}
            fields={[{ key: "name", label: "Nombre" }, { key: "price", label: "Precio del paquete (Q)", type: "number" }, { key: "validity_days", label: "Vigencia (días)", type: "number" },
              { key: "active", label: "Disponible para venta", type: "switch" }, { key: "items", label: "Servicios incluidos", type: "pkgitems" }, { key: "description", label: "Descripción", type: "textarea" }]}
            columns={[{ key: "name", label: "Paquete" }, { key: "items", label: "Incluye", render: (r) => (r.items || []).map((i) => `${i.qty} x ${i.service_name}`).join(", ") },
              { key: "price", label: "Precio", render: (r) => money(r.price) }, { key: "validity_days", label: "Vigencia", render: (r) => `${r.validity_days} días` },
              { key: "active", label: "Disponible", render: (r) => (r.active === false ? "No" : "Sí") }]} />
        </TabsContent>
      </Tabs>
      {sell && <SellPackageDialog onClose={() => setSell(false)} onDone={() => { setSell(false); setTick((t) => t + 1); }} />}
    </div>
  );
}
