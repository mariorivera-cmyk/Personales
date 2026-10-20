import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { MessageCircle, RefreshCw, Unplug, Clock, CheckCircle2 } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Panel, Label } from "@/components/Common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const ST = {
  APPROVED: ["Aprobada", "bg-emerald-100 text-emerald-800"], PENDING: ["En revisión", "bg-amber-100 text-amber-800"],
  REJECTED: ["Rechazada", "bg-red-100 text-red-800"], ERROR: ["Error al crear", "bg-red-100 text-red-800"],
  PAUSED: ["Pausada", "bg-slate-200 text-slate-700"], DISABLED: ["Deshabilitada", "bg-slate-200 text-slate-700"],
  NOT_CREATED: ["Se crea al conectar", "bg-slate-100 text-slate-600"],
};

function loadSdk(appId, version) {
  return new Promise((resolve) => {
    if (window.FB) { resolve(window.FB); return; }
    window.fbAsyncInit = () => { window.FB.init({ appId, autoLogAppEvents: true, xfbml: false, version }); resolve(window.FB); };
    const s = document.createElement("script");
    s.src = "https://connect.facebook.net/es_LA/sdk.js"; s.async = true; s.defer = true; s.crossOrigin = "anonymous";
    document.body.appendChild(s);
  });
}

function Templates({ rows }) {
  return (
    <div className="mt-4 overflow-x-auto rounded-xl border" data-testid="wa-templates-table">
      <table className="w-full text-sm">
        <thead className="bg-secondary/60 text-left text-xs uppercase tracking-wider text-slate-500"><tr><th className="px-3 py-2">Plantilla</th><th className="px-3 py-2">Tipo</th><th className="px-3 py-2">Estado en Meta</th></tr></thead>
        <tbody>{rows.map((t) => {
          const [txt, cls] = ST[t.status] || [t.status, "bg-slate-100 text-slate-600"];
          return (
            <tr key={t.name} className="border-t" data-testid={`wa-template-${t.name}`}>
              <td className="px-3 py-2"><div className="font-medium">{t.label}</div><div className="text-xs text-muted-foreground">{t.name}</div></td>
              <td className="px-3 py-2 text-xs">{{ UTILITY: "Utilidad", MARKETING: "Marketing", AUTHENTICATION: "Autenticación" }[t.category]}</td>
              <td className="px-3 py-2"><span className={`rounded-full px-2 py-0.5 text-xs font-medium ${cls}`} data-testid={`wa-template-status-${t.name}`}>{txt}</span>{t.reason && <div className="mt-1 text-xs text-red-700">{t.reason}</div>}</td>
            </tr>
          );
        })}</tbody>
      </table>
    </div>
  );
}

function Connected({ s, reload, setS }) {
  const [busy, setBusy] = useState(false);
  const run = async (path, msg) => {
    setBusy(true);
    try { setS((await api.post(path)).data); toast.success(msg); } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const c = s.connection;
  return (
    <div data-testid="wa-connected">
      <div className="flex flex-wrap items-center gap-3 rounded-xl bg-emerald-50 p-4">
        <CheckCircle2 className="h-6 w-6 text-emerald-600" />
        <div className="flex-1"><div className="font-semibold" data-testid="wa-connected-number">{c.verified_name} · {c.display_phone_number}</div><div className="text-xs text-muted-foreground">Conectado el {c.connected_at?.slice(0, 10)}. Los mensajes ya salen por WhatsApp real.</div></div>
        <Button variant="outline" size="sm" disabled={busy} onClick={() => run("/wa-cloud/templates/sync", "Estado de plantillas actualizado")} data-testid="wa-sync-btn"><RefreshCw className="mr-1 h-4 w-4" />Actualizar estado</Button>
        <Button variant="outline" size="sm" disabled={busy} onClick={() => window.confirm("¿Desconectar WhatsApp? Los mensajes volverán al simulador.") && run("/wa-cloud/disconnect", "WhatsApp desconectado")} data-testid="wa-disconnect-btn"><Unplug className="mr-1 h-4 w-4" />Desconectar</Button>
      </div>
      <Templates rows={s.templates} />
    </div>
  );
}

function ConnectButton({ s, setS }) {
  const [busy, setBusy] = useState(false);
  const [pin, setPin] = useState("");
  const session = useRef({});
  const connect = async () => {
    if (pin && !/^\d{6}$/.test(pin)) { toast.error("El PIN debe tener 6 dígitos"); return; }
    setBusy(true);
    const FB = await loadSdk(s.app_id, s.graph_version);
    const onMsg = (ev) => {
      if (!String(ev.origin).endsWith("facebook.com")) return;
      try { const d = JSON.parse(ev.data); if (d.type === "WA_EMBEDDED_SIGNUP" && d.data?.waba_id) session.current = d.data; } catch { /* ignore */ }
    };
    window.addEventListener("message", onMsg);
    FB.login((resp) => {
      const code = resp?.authResponse?.code;
      if (!code) { window.removeEventListener("message", onMsg); setBusy(false); toast.error("Conexión cancelada"); return; }
      setTimeout(async () => {
        window.removeEventListener("message", onMsg);
        try {
          const r = await api.post("/wa-cloud/connect", { code, waba_id: session.current.waba_id, phone_number_id: session.current.phone_number_id, pin });
          setS(r.data); toast.success("¡WhatsApp conectado! Las plantillas se enviaron a revisión de Meta.");
        } catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
      }, 800);
    }, { config_id: s.config_id, response_type: "code", override_default_response_type: true, extras: { setup: {}, sessionInfoVersion: "3" } });
  };
  return (
    <div className="space-y-4">
      <div className="max-w-xs"><Label>PIN de verificación en dos pasos (opcional)</Label><Input value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 6))} placeholder="6 dígitos" data-testid="wa-pin-input" /><p className="mt-1 text-xs text-muted-foreground">Solo si su número es nuevo en WhatsApp Business Platform.</p></div>
      <Button size="lg" className="bg-[#25D366] text-white hover:bg-[#1ebe5b]" disabled={busy} onClick={connect} data-testid="wa-connect-btn"><MessageCircle className="mr-2 h-5 w-5" />{busy ? "Conectando…" : "Conectar con WhatsApp"}</Button>
    </div>
  );
}

export function WhatsAppConnect() {
  const [s, setS] = useState(null);
  const load = () => api.get("/wa-cloud/status").then((r) => setS(r.data)).catch((e) => toast.error(errMsg(e)));
  useEffect(() => { load(); }, []);
  if (!s) return null;
  const connected = s.connection?.status === "connected";
  return (
    <Panel title="WhatsApp oficial (Meta)" testid="wa-connect-panel">
      <p className="mb-4 text-sm text-muted-foreground">Conecte el número de WhatsApp de su salón. Se abrirá la ventana oficial de Meta para iniciar sesión y elegir el número. Al terminar, SalonFlow crea las 8 plantillas de mensajes y los recordatorios, confirmaciones y el asistente funcionarán por WhatsApp real.</p>
      {connected ? <Connected s={s} setS={setS} reload={load} /> : s.enabled ? <ConnectButton s={s} setS={setS} /> : (
        <div data-testid="wa-pending">
          <Button size="lg" disabled variant="secondary" className="disabled:opacity-100 text-slate-600" data-testid="wa-connect-btn-pending"><Clock className="mr-2 h-5 w-5" />Pendiente de configuración</Button>
          <p className="mt-2 text-xs text-muted-foreground">La plataforma aún está activando la conexión con Meta. Mientras tanto, los mensajes se registran en el simulador de WhatsApp.</p>
        </div>
      )}
      {!connected && <Templates rows={s.templates} />}
    </Panel>
  );
}
