import { useState } from "react";
import { toast } from "sonner";
import { Pencil, Trash2, Check, X } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

function CategoryRow({ cat, reload }) {
  const [edit, setEdit] = useState(null);
  const run = async (fn, ok) => { try { await fn(); toast.success(ok); setEdit(null); reload(); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <li className="flex items-center gap-2 border-t py-2 first:border-t-0" data-testid={`category-row-${cat.id}`}>
      {edit !== null ? <input className="field h-9 flex-1" value={edit} onChange={(e) => setEdit(e.target.value)} autoFocus data-testid={`category-edit-input-${cat.id}`} />
        : <span className="flex-1 text-sm font-medium">{cat.name} <span className="text-xs text-muted-foreground">· {cat.services} servicio(s)</span></span>}
      {edit !== null ? <>
        <Button size="icon" variant="ghost" onClick={() => run(() => api.put(`/service-categories/${cat.id}`, { name: edit }), "Categoría actualizada")} data-testid={`category-save-${cat.id}`}><Check className="h-4 w-4" /></Button>
        <Button size="icon" variant="ghost" onClick={() => setEdit(null)} data-testid={`category-cancel-${cat.id}`}><X className="h-4 w-4" /></Button>
      </> : <>
        <Button size="icon" variant="ghost" onClick={() => setEdit(cat.name)} data-testid={`category-rename-${cat.id}`}><Pencil className="h-4 w-4" /></Button>
        <Button size="icon" variant="ghost" onClick={() => run(() => api.delete(`/service-categories/${cat.id}`), "Categoría eliminada")} data-testid={`category-delete-${cat.id}`}><Trash2 className="h-4 w-4 text-rose-600" /></Button>
      </>}
    </li>
  );
}

export function CategoriesButton({ onDone }) {
  const [open, setOpen] = useState(false);
  const [cats, setCats] = useState([]);
  const [name, setName] = useState("");
  const load = () => api.get("/service-categories").then((r) => setCats(r.data)).catch((e) => toast.error(errMsg(e)));
  const add = async (e) => {
    e.preventDefault();
    try { await api.post("/service-categories", { name }); toast.success("Categoría creada"); setName(""); load(); } catch (err) { toast.error(errMsg(err)); }
  };
  const close = (o) => { setOpen(o); if (!o) onDone?.(); };
  return (
    <>
      <Button variant="outline" onClick={() => { load(); setOpen(true); }} data-testid="service-categories-btn">Categorías</Button>
      <Dialog open={open} onOpenChange={close}>
        <DialogContent className="max-w-md" data-testid="categories-dialog">
          <DialogHeader><DialogTitle className="font-heading">Categorías de servicio</DialogTitle></DialogHeader>
          <form onSubmit={add} className="flex gap-2">
            <input className="field flex-1" placeholder="Ej.: Color, Uñas, Tratamientos" value={name} onChange={(e) => setName(e.target.value)} data-testid="category-name-input" />
            <Button type="submit" disabled={!name.trim()} data-testid="category-add-btn">Agregar</Button>
          </form>
          <ul className="max-h-80 overflow-auto" data-testid="categories-list">
            {cats.map((c) => <CategoryRow key={c.id} cat={c} reload={load} />)}
            {!cats.length && <li className="py-4 text-center text-sm text-muted-foreground">Aún no hay categorías. Cree la primera.</li>}
          </ul>
          <p className="text-xs text-muted-foreground">Renombrar una categoría actualiza todos sus servicios. Solo se puede eliminar si ningún servicio la usa.</p>
        </DialogContent>
      </Dialog>
    </>
  );
}
