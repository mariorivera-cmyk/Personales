import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Star, EyeOff, Eye } from "lucide-react";
import { api, errMsg, money } from "@/lib/api";
import { PageHeader, Panel, Kpi, Label, EmptyState } from "@/components/Common";
import { Button } from "@/components/ui/button";
import CrudPage from "@/components/CrudPage";
import { PaymentRows } from "@/components/Checkout";

export function Inventory() {
  const [d, setD] = useState(null);
  const [sale, setSale] = useState({ items: [{ product_id: "", qty: 1 }] });
  const [rows, setRows] = useState([{ method: "cash", amount: 0 }]);
  const [key, setKey] = useState(0);
  const [branches, setBranches] = useState([]);
  useEffect(() => { api.get("/branches").then((r) => { setBranches(r.data); setSale((s) => ({ ...s, branch_id: s.branch_id || r.data[0]?.id })); }); }, []);
  const load = () => api.get("/inventory").then((r) => setD(r.data));
  useEffect(() => { load(); }, [key]);
  if (!d) return null;
  const total = sale.items.reduce((a, it) => a + (d.products.find((p) => p.id === it.product_id)?.price || 0) * Number(it.qty || 0), 0);
  const sell = async () => {
    try { await api.post("/products/sale", { ...sale, payments: rows }); toast.success("Venta registrada en caja"); setSale({ items: [{ product_id: "", qty: 1 }], branch_id: sale.branch_id }); setRows([{ method: "cash", amount: 0 }]); setKey(key + 1); } catch (e) { toast.error(errMsg(e)); }
  };
  const adjust = async (p) => {
    const qty = window.prompt(`Ajuste de ${p.name} (use negativo para restar)`);
    if (!qty) return;
    const reason = window.prompt("Motivo del ajuste");
    try { await api.post(`/products/${p.id}/adjust`, { qty: Number(qty), reason }); setKey(key + 1); } catch (e) { toast.error(errMsg(e)); }
  };
  const setItem = (i, k, v) => setSale({ ...sale, items: sale.items.map((x, j) => (j === i ? { ...x, [k]: v } : x)) });
  return (
    <div data-testid="inventory-page">
      <PageHeader title="Inventario y productos" subtitle={`Valor del inventario: ${money(d.value)}`} />
      <div className="mb-8 grid gap-6 lg:grid-cols-2">
        <Panel title="Venta en mostrador" testid="counter-sale">
          <select className="field mb-2" value={sale.branch_id || ""} onChange={(e) => setSale({ ...sale, branch_id: e.target.value })} data-testid="sale-branch">{branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select>
          {sale.items.map((it, i) => (
            <div key={i} className="mb-2 flex gap-2">
              <select className="field" value={it.product_id} onChange={(e) => setItem(i, "product_id", e.target.value)} data-testid={`sale-product-${i}`}>
                <option value="">— Producto —</option>{d.products.map((p) => <option key={p.id} value={p.id}>{p.name} · {money(p.price)} · exist. {p.stock}</option>)}
              </select>
              <input type="number" className="field w-24" value={it.qty} onChange={(e) => setItem(i, "qty", e.target.value)} data-testid={`sale-qty-${i}`} />
            </div>
          ))}
          <button className="mb-3 text-sm text-primary" onClick={() => setSale({ ...sale, items: [...sale.items, { product_id: "", qty: 1 }] })}>+ Agregar producto</button>
          <div className="mb-2 text-sm">Total: <b>{money(total)}</b></div>
          <PaymentRows rows={rows} setRows={setRows} total={total} />
          <Button className="mt-3" onClick={sell} data-testid="sale-submit">Registrar venta</Button>
        </Panel>
        <Panel title="Movimientos recientes">
          <ul className="max-h-72 space-y-1 overflow-auto text-sm">{d.moves.map((m) => <li key={m.id} className="flex justify-between"><span>{m.created_at.slice(0, 16).replace("T", " ")} · {m.product_name} · {m.reason}</span><b className={m.qty < 0 ? "text-rose-600" : "text-emerald-700"}>{m.qty > 0 ? "+" : ""}{m.qty}</b></li>)}</ul>
        </Panel>
      </div>
      <CrudPage key={key} title="Productos" endpoint="/products" testid="products" defaults={{ stock: 0, min_stock: 2 }} onSaved={load}
        beforeSave={(p) => !(Number(p.cost) > 0 && Number(p.price) < Number(p.cost)) || window.confirm(`El precio de venta (Q${Number(p.price || 0).toFixed(2)}) es menor al costo (Q${Number(p.cost).toFixed(2)}). ¿Desea guardar de todas formas?`)}
        fields={[{ key: "name", label: "Nombre" }, { key: "sku", label: "Código" }, { key: "cost", label: "Costo", type: "number" }, { key: "price", label: "Precio de venta", type: "number" },
          { key: "stock", label: "Existencia", type: "number" }, { key: "min_stock", label: "Mínimo", type: "number" }]}
        columns={[{ key: "name", label: "Producto" }, { key: "price", label: "Precio", render: (r) => money(r.price) }, { key: "cost", label: "Costo", render: (r) => money(r.cost) },
          { key: "stock", label: "Existencia", render: (r) => <span className={Number(r.stock) <= Number(r.min_stock) ? "font-semibold text-rose-600" : ""}>{r.stock} (mín. {r.min_stock})</span> }]}
        rowActions={(p) => <Button size="sm" variant="outline" onClick={() => adjust(p)} data-testid={`adjust-${p.id}`}>Ajustar</Button>} />
    </div>
  );
}

export function ReviewsGallery() {
  const [revs, setRevs] = useState(null);
  const load = () => api.get("/reviews").then((r) => setRevs(r.data));
  useEffect(() => { load(); }, []);
  const toggle = async (r) => { await api.put(`/reviews/${r.id}`, { hidden: !r.hidden }); load(); };
  const avg = revs?.length ? (revs.reduce((a, r) => a + r.rating, 0) / revs.length).toFixed(1) : "—";
  return (
    <div data-testid="reviews-page">
      <PageHeader title="Reseñas y galería" subtitle="Solo clientas con cita atendida pueden calificar" />
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4"><Kpi label="Promedio" value={avg} icon={Star} testid="reviews-avg" /><Kpi label="Reseñas" value={revs?.length || 0} testid="reviews-count" /></div>
      <Panel title="Reseñas" className="mb-8" testid="reviews-list">
        {!revs?.length ? <EmptyState text="Aún no hay reseñas. Se invita a calificar al marcar una cita como Atendida." /> : (
          <ul className="space-y-2">{revs.map((r) => (
            <li key={r.id} className={`flex items-start justify-between rounded-lg border p-3 text-sm ${r.hidden ? "opacity-50" : ""}`}>
              <div><div className="font-medium">{"★".repeat(r.rating)}{"☆".repeat(5 - r.rating)} · {r.client_name} · {r.service_name}</div><div className="text-slate-600">{r.comment}</div></div>
              <Button size="sm" variant="ghost" onClick={() => toggle(r)} data-testid={`review-toggle-${r.id}`}>{r.hidden ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}</Button>
            </li>
          ))}</ul>
        )}
      </Panel>
      <CrudPage title="Galería de trabajos" endpoint="/gallery" testid="gallery"
        fields={[{ key: "url", label: "Foto", type: "image" }, { key: "caption", label: "Descripción" }, { key: "service_id", label: "Servicio", type: "select", source: "/services" }]}
        columns={[{ key: "url", label: "Foto", render: (r) => r.url && <img src={`${process.env.REACT_APP_BACKEND_URL}${r.url}`} alt={r.caption} className="h-14 w-14 rounded-lg object-cover" /> }, { key: "caption", label: "Descripción" }]} />
    </div>
  );
}

export function LabelHelp({ children }) { return <Label>{children}</Label>; }
