import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg, money } from "@/lib/api";
import { Label, Panel } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { PaymentRows } from "@/components/Checkout";

export const PK_STATUS = {
  active: ["Vigente", "bg-emerald-100 text-emerald-800"], exhausted: ["Agotado", "bg-slate-200 text-slate-700"],
  expired: ["Vencido", "bg-amber-100 text-amber-800"], voided: ["Anulado", "bg-red-100 text-red-800"],
};

export const PkgBadge = ({ status, testid }) => {
  const [t, cls] = PK_STATUS[status] || [status, ""];
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${cls}`} data-testid={testid}>{t}</span>;
};

export const PkgItems = ({ cp }) => (
  <div className="text-xs text-muted-foreground">{cp.items.map((i) => `${i.service_name}: ${i.qty - i.used} de ${i.qty}`).join(" · ")}</div>
);

function ClientPicker({ client, setClient }) {
  const [phone, setPhone] = useState("");
  const find = async () => {
    try {
      const r = await api.get("/clients/lookup", { params: { phone } });
      if (!r.data.exists) { toast.error("No existe una clienta con ese teléfono. Regístrela primero en Clientes."); return; }
      setClient(r.data.client);
    } catch (e) { toast.error(errMsg(e)); }
  };
  if (client) return <div className="text-sm">Clienta: <b data-testid="sell-client-name">{client.name}</b></div>;
  return (
    <div><Label>Teléfono de la clienta</Label>
      <div className="flex gap-2"><input className="field" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+502 5555 5555" data-testid="sell-client-phone" /><Button type="button" variant="outline" onClick={find} data-testid="sell-client-find">Buscar</Button></div>
    </div>
  );
}

export function SellPackageDialog({ client: initial, onClose, onDone }) {
  const [client, setClient] = useState(initial || null);
  const [pkgs, setPkgs] = useState([]);
  const [branches, setBranches] = useState([]);
  const [f, setF] = useState({ package_id: "", branch_id: "" });
  const [rows, setRows] = useState([]);
  useEffect(() => {
    api.get("/packages").then((r) => setPkgs(r.data.filter((p) => p.active !== false)));
    api.get("/branches").then((r) => { setBranches(r.data); setF((s) => ({ ...s, branch_id: r.data[0]?.id || "" })); });
  }, []);
  const pkg = pkgs.find((p) => p.id === f.package_id);
  const pick = (id) => { setF({ ...f, package_id: id }); const p = pkgs.find((x) => x.id === id); setRows(p ? [{ method: "cash", amount: p.price.toFixed(2) }] : []); };
  const paid = rows.reduce((a, r) => a + Number(r.amount || 0), 0);
  const submit = async () => {
    try { await api.post("/client-packages", { client_id: client.id, ...f, payments: rows }); toast.success("Paquete vendido y activado"); onDone(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md" data-testid="sell-package-dialog">
        <DialogHeader><DialogTitle className="font-heading">Vender paquete</DialogTitle></DialogHeader>
        <div className="space-y-3 text-sm">
          <ClientPicker client={client} setClient={setClient} />
          <div><Label>Paquete</Label><select className="field" value={f.package_id} onChange={(e) => pick(e.target.value)} data-testid="sell-package-select">
            <option value="">— Seleccione —</option>{pkgs.map((p) => <option key={p.id} value={p.id}>{p.name} · {money(p.price)}</option>)}</select></div>
          {pkg && <div className="rounded-lg bg-secondary/60 p-3 text-xs" data-testid="sell-package-detail">{pkg.items.map((i) => `${i.qty} x ${i.service_name}`).join(" · ")} · Vigencia {pkg.validity_days} días</div>}
          {branches.length > 1 && <div><Label>Sucursal</Label><select className="field" value={f.branch_id} onChange={(e) => setF({ ...f, branch_id: e.target.value })} data-testid="sell-branch-select">{branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></div>}
          {pkg && <PaymentRows rows={rows} setRows={setRows} total={pkg.price} />}
          <Button className="w-full" disabled={!client || !pkg || Math.abs(paid - (pkg?.price || 0)) > 0.01} onClick={submit} data-testid="sell-package-submit">Cobrar y activar paquete</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function UseRow({ cp, reload }) {
  const use = async (i) => {
    if (!window.confirm(`¿Descontar 1 sesión de ${i.service_name} sin cita?`)) return;
    try { await api.post(`/client-packages/${cp.id}/use`, { service_id: i.service_id, note: "Uso manual desde ficha" }); toast.success("Sesión descontada"); reload(); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <li className="rounded-lg border p-3" data-testid={`client-pkg-${cp.id}`}>
      <div className="flex items-center justify-between gap-2"><b>{cp.name}</b><PkgBadge status={cp.status} testid={`client-pkg-status-${cp.id}`} /></div>
      <div className="text-xs text-muted-foreground">Vence {cp.expires} · {cp.remaining} de {cp.total} sesiones disponibles</div>
      <div className="mt-2 space-y-1">{cp.items.map((i) => (
        <div key={i.service_id} className="flex items-center justify-between text-xs">
          <span>{i.service_name}: {i.qty - i.used} de {i.qty}</span>
          {cp.status === "active" && i.used < i.qty && <button className="text-primary underline" onClick={() => use(i)} data-testid={`client-pkg-use-${cp.id}-${i.service_id}`}>Usar sesión</button>}
        </div>))}
      </div>
    </li>
  );
}

export function ClientPackagesPanel({ client }) {
  const [rows, setRows] = useState([]);
  const [sell, setSell] = useState(false);
  const load = () => api.get("/client-packages", { params: { client_id: client.id } }).then((r) => setRows(r.data)).catch(() => setRows([]));
  useEffect(() => { load(); }, [client.id]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Panel title="Paquetes" className="mt-6" testid="client-packages-panel"
      action={<Button size="sm" onClick={() => setSell(true)} data-testid="client-sell-package-btn">Vender paquete</Button>}>
      {rows.length === 0 ? <p className="text-sm text-muted-foreground">Sin paquetes.</p> : <ul className="grid gap-3 md:grid-cols-2">{rows.map((cp) => <UseRow key={cp.id} cp={cp} reload={load} />)}</ul>}
      {sell && <SellPackageDialog client={client} onClose={() => setSell(false)} onDone={() => { setSell(false); load(); }} />}
    </Panel>
  );
}
