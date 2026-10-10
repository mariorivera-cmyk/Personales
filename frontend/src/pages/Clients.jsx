import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Plus, Search } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { PageHeader, EmptyState } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { FormDialog } from "@/components/CrudPage";

const FIELDS = [
  { key: "phone", label: "Teléfono (WhatsApp)", placeholder: "+502..." }, { key: "name", label: "Nombre" },
  { key: "email", label: "Correo", type: "email" }, { key: "birthdate", label: "Fecha de nacimiento", type: "date" },
  { key: "gender", label: "Género", type: "select", options: [{ value: "F", label: "Femenino" }, { value: "M", label: "Masculino" }, { value: "O", label: "Otro" }] },
  { key: "referred_by", label: "Referido por (teléfono)" },
];

export default function Clients() {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState([]);
  const [open, setOpen] = useState(false);
  const nav = useNavigate();
  const load = () => api.get("/clients", { params: { q } }).then((r) => setRows(r.data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [q]); // eslint-disable-line
  return (
    <div data-testid="clients-page">
      <PageHeader title="Clientes" subtitle="Ficha asociada al número telefónico de WhatsApp"
        action={<Button onClick={() => setOpen(true)} data-testid="new-client-btn"><Plus className="mr-1 h-4 w-4" />Nuevo cliente</Button>} />
      <div className="relative mb-4 max-w-sm">
        <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
        <input className="field pl-9" placeholder="Buscar por nombre o teléfono" value={q} onChange={(e) => setQ(e.target.value)} data-testid="clients-search-input" />
      </div>
      {rows.length === 0 ? <EmptyState text="Sin clientes" /> : (
        <div className="overflow-x-auto rounded-2xl border bg-white">
          <table className="w-full text-sm" data-testid="clients-table">
            <thead className="bg-secondary/60 text-left text-xs uppercase tracking-wider text-slate-500">
              <tr><th className="px-4 py-3">Nombre</th><th className="px-4 py-3">Teléfono</th><th className="px-4 py-3">Correo</th><th className="px-4 py-3">Puntos</th><th className="px-4 py-3">Membresía</th></tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id} onClick={() => nav(`/app/clientes/${c.id}`)} className="cursor-pointer border-t hover:bg-secondary/30" data-testid={`client-row-${c.id}`}>
                  <td className="px-4 py-3 font-medium">{c.name}</td><td className="px-4 py-3 font-mono text-xs">{c.phone}</td>
                  <td className="px-4 py-3">{c.email}</td><td className="px-4 py-3">{c.points || 0}</td><td className="px-4 py-3">{c.membership || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <FormDialog open={open} onOpenChange={setOpen} title="Nuevo cliente" fields={FIELDS} testid="client-form"
        onSubmit={async (f) => { const r = await api.post("/clients", f); toast.success("Cliente creado"); nav(`/app/clientes/${r.data.id}`); }} />
    </div>
  );
}
