import { useState } from "react";
import { toast } from "sonner";
import { PlayCircle, FlaskConical, PauseCircle, XCircle, Trash2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";

const OPTIONS = [
  { key: "active", label: "Activa", icon: PlayCircle, desc: "Sigue funcionando con normalidad.", cls: "text-emerald-700" },
  { key: "trial", label: "Modo prueba", icon: FlaskConical, desc: "30 días de prueba a partir de hoy.", cls: "text-sky-700" },
  { key: "paused", label: "En pausa", icon: PauseCircle, desc: "Nadie de la empresa puede entrar. Portal y WhatsApp detenidos. Los datos se conservan.", cls: "text-violet-700" },
  { key: "cancelled", label: "Cancelada", icon: XCircle, desc: "Nadie puede entrar. Los datos se conservan 2 meses y luego se borran automáticamente.", cls: "text-rose-700" },
];

function StatusConfirm({ opt, company, onClose, onDone }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const go = async () => {
    setBusy(true);
    try { await api.post(`/admin/companies/${company.id}/status`, { status: opt.key, reason }); toast.success(`Estado cambiado a ${opt.label}`); onDone(); onClose(); }
    catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md" data-testid="status-confirm-dialog">
        <DialogHeader><DialogTitle>¿Cambiar «{company.name}» a {opt.label}?</DialogTitle><DialogDescription>{opt.desc}</DialogDescription></DialogHeader>
        <input className="field" placeholder="Motivo (opcional)" value={reason} onChange={(e) => setReason(e.target.value)} data-testid="status-reason-input" />
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} data-testid="status-confirm-cancel">Cancelar</Button>
          <Button onClick={go} disabled={busy} variant={opt.key === "cancelled" ? "destructive" : "default"} data-testid="status-confirm-ok">Confirmar</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function CompanyStatusPanel({ company, onDone }) {
  const [pick, setPick] = useState(null);
  return (
    <div data-testid="company-status-panel">
      <h4 className="mb-2 font-semibold">Estado de la empresa</h4>
      <div className="grid grid-cols-2 gap-2">
        {OPTIONS.map((o) => {
          const cur = company.status === o.key;
          return (
            <button key={o.key} type="button" disabled={cur} onClick={() => setPick(o)} data-testid={`company-status-${o.key}-btn`}
              className={`rounded-xl border p-3 text-left transition-colors ${cur ? "border-primary bg-primary/5" : "hover:bg-secondary/60"}`}>
              <div className={`flex items-center gap-1.5 font-semibold ${o.cls}`}><o.icon className="h-4 w-4" />{o.label}{cur && <span className="ml-auto text-[10px] uppercase text-muted-foreground">Actual</span>}</div>
              <p className="mt-1 text-xs text-muted-foreground">{o.desc}</p>
            </button>
          );
        })}
      </div>
      {company.status === "trial" && company.trial_ends && <p className="mt-2 text-xs text-muted-foreground" data-testid="company-trial-ends">Prueba hasta {company.trial_ends}</p>}
      {company.status === "cancelled" && company.purge_after && <p className="mt-2 text-xs font-medium text-rose-700" data-testid="company-purge-date">Los datos se borrarán el {company.purge_after}. Reactívela antes para conservarlos.</p>}
      {pick && <StatusConfirm opt={pick} company={company} onClose={() => setPick(null)} onDone={onDone} />}
    </div>
  );
}

export function DeleteCompany({ company, onDeleted }) {
  const [open, setOpen] = useState(false);
  const [word, setWord] = useState("");
  const del = async () => {
    try { await api.delete(`/admin/companies/${company.id}`, { data: { confirm: word } }); toast.success("Empresa eliminada definitivamente"); setOpen(false); onDeleted(); }
    catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div className="rounded-xl border border-rose-200 bg-rose-50/50 p-3" data-testid="company-delete-zone">
      <h4 className="font-semibold text-rose-800">Zona de peligro</h4>
      <p className="mb-2 text-xs text-rose-700">Borra la empresa y todos sus datos (clientes, citas, ventas, usuarios). No se puede deshacer.</p>
      <Button variant="destructive" size="sm" onClick={() => { setWord(""); setOpen(true); }} data-testid="company-delete-btn"><Trash2 className="mr-1 h-4 w-4" />Eliminar empresa</Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md" data-testid="company-delete-dialog">
          <DialogHeader><DialogTitle>Eliminar «{company.name}»</DialogTitle><DialogDescription>Esta acción borra todos los datos de la empresa de forma permanente. Para confirmar escriba la palabra de seguridad <b>ELIMINAR</b>.</DialogDescription></DialogHeader>
          <input className="field" value={word} onChange={(e) => setWord(e.target.value)} placeholder="ELIMINAR" autoComplete="off" data-testid="company-delete-word" />
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setOpen(false)} data-testid="company-delete-cancel">Cancelar</Button>
            <Button variant="destructive" disabled={word !== "ELIMINAR"} onClick={del} data-testid="company-delete-confirm">Eliminar definitivamente</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
