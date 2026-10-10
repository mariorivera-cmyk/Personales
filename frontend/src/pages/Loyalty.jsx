import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, errMsg } from "@/lib/api";
import { PageHeader, Panel, Label } from "@/components/Common";
import { Button } from "@/components/ui/button";
import CrudPage from "@/components/CrudPage";

export default function Loyalty() {
  const [d, setD] = useState(null);
  const [cfg, setCfg] = useState({});
  const [pts, setPts] = useState({});
  const load = () => api.get("/loyalty").then((r) => { setD(r.data); setCfg(r.data.config); }).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, []);
  const save = async () => { try { await api.put("/loyalty", cfg); toast.success("Programa actualizado"); } catch (e) { toast.error(errMsg(e)); } };
  const move = async (c, redeem) => {
    try {
      const r = await api.post("/loyalty/points", { client_id: c.id, points: Number(pts[c.id] || 0), redeem });
      toast.success(redeem ? `Canjeados. Valor: Q${r.data.value}` : "Puntos agregados");
      load();
    } catch (e) { toast.error(errMsg(e)); }
  };
  if (!d) return null;
  const mem = cfg.memberships || [];
  const setMem = (i, k, v) => setCfg({ ...cfg, memberships: mem.map((m, j) => (j === i ? { ...m, [k]: v } : m)) });
  return (
    <div data-testid="loyalty-page">
      <PageHeader title="Programa de fidelización" subtitle="Puntos, membresías, cupones, referidos y redención" />
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Reglas de puntos" testid="loyalty-config">
          <div className="grid grid-cols-3 gap-3">
            <div><Label>Puntos por cada Q100</Label><input type="number" className="field" value={cfg.points_per_100 ?? ""} onChange={(e) => setCfg({ ...cfg, points_per_100: Number(e.target.value) })} data-testid="loyalty-points-per-100" /></div>
            <div><Label>Valor por punto (Q)</Label><input type="number" step="0.01" className="field" value={cfg.redeem_value ?? ""} onChange={(e) => setCfg({ ...cfg, redeem_value: Number(e.target.value) })} data-testid="loyalty-redeem-value" /></div>
            <div><Label>Bono por referido</Label><input type="number" className="field" value={cfg.referral_points ?? ""} onChange={(e) => setCfg({ ...cfg, referral_points: Number(e.target.value) })} data-testid="loyalty-referral-points" /></div>
          </div>
          <div className="mt-5"><Label>Membresías</Label>
            {mem.map((m, i) => (
              <div key={i} className="mb-2 grid grid-cols-3 gap-2">
                <input className="field" placeholder="Nombre" value={m.name} onChange={(e) => setMem(i, "name", e.target.value)} />
                <input className="field" type="number" placeholder="% descuento" value={m.discount} onChange={(e) => setMem(i, "discount", Number(e.target.value))} />
                <input className="field" type="number" placeholder="Precio mensual" value={m.price} onChange={(e) => setMem(i, "price", Number(e.target.value))} />
              </div>
            ))}
            <button className="text-sm text-primary underline" onClick={() => setCfg({ ...cfg, memberships: [...mem, { name: "", discount: 0, price: 0 }] })} data-testid="add-membership-btn">+ Agregar membresía</button>
          </div>
          <Button className="mt-4" onClick={save} data-testid="loyalty-save-btn">Guardar</Button>
        </Panel>
        <Panel title="Top clientes por puntos" testid="loyalty-top">
          <ul className="max-h-96 space-y-2 overflow-auto">
            {d.top.map((c) => (
              <li key={c.id} className="flex items-center gap-2 rounded-lg border p-2 text-sm">
                <div className="flex-1"><div className="font-medium">{c.name}</div><div className="text-xs text-muted-foreground">{c.points || 0} pts {c.membership && `· ${c.membership}`}</div></div>
                <input type="number" className="field h-8 w-20" placeholder="pts" value={pts[c.id] || ""} onChange={(e) => setPts({ ...pts, [c.id]: e.target.value })} data-testid={`points-input-${c.id}`} />
                <Button size="sm" variant="outline" onClick={() => move(c, false)} data-testid={`points-add-${c.id}`}>+</Button>
                <Button size="sm" onClick={() => move(c, true)} data-testid={`points-redeem-${c.id}`}>Canjear</Button>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
      <div className="mt-8">
        <h3 className="mb-3 font-heading text-lg font-semibold">Cupones y bonificaciones</h3>
        <CrudPage embedded endpoint="/coupons" testid="loyalty-coupons"
          fields={[{ key: "code", label: "Código" }, { key: "percent", label: "% descuento", type: "number" }, { key: "description", label: "Descripción", full: true }, { key: "expires", label: "Vence", type: "date" }]}
          columns={[{ key: "code", label: "Código" }, { key: "percent", label: "%" }, { key: "description", label: "Descripción" }, { key: "expires", label: "Vence" }]} />
      </div>
    </div>
  );
}
