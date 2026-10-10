import { useEffect, useRef, useState, useCallback } from "react";
import { toast } from "sonner";
import { Send, Bot, Phone, Plus, Info } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { useAuth } from "@/context/Auth";
import { PageHeader, Panel } from "@/components/Common";
import { Button } from "@/components/ui/button";

const KIND = { reminder: "Recordatorio", campaign: "Campaña", waitlist: "Lista de espera", confirmation: "Confirmación" };

export default function WhatsApp() {
  const { company } = useAuth();
  const [convs, setConvs] = useState([]);
  const [phone, setPhone] = useState("+50259990000");
  const [msgs, setMsgs] = useState([]);
  const [text, setText] = useState("");
  const [typing, setTyping] = useState(false);
  const end = useRef(null);
  const loadConvs = () => api.get("/wa/conversations").then((r) => setConvs(r.data)).catch(() => {});
  const loadMsgs = useCallback(() => api.get("/wa/messages", { params: { phone } }).then((r) => setMsgs(r.data)).catch(() => {}), [phone]);
  useEffect(() => { loadConvs(); }, []);
  useEffect(() => { loadMsgs(); const t = setInterval(loadMsgs, 5000); return () => clearInterval(t); }, [loadMsgs]);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, typing]);
  const send = async (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    const t = text;
    setText("");
    setMsgs((m) => [...m, { id: "tmp", direction: "in", text: t, created_at: new Date().toISOString() }]);
    setTyping(true);
    try {
      await api.post("/wa/inbound", { to: company.whatsapp_number, from_phone: phone, text: t });
    } catch (err) { toast.error(errMsg(err)); }
    setTyping(false);
    loadMsgs();
    loadConvs();
  };
  const webhook = `${process.env.REACT_APP_BACKEND_URL}/api/wa/webhook`;
  return (
    <div data-testid="whatsapp-page">
      <PageHeader title="WhatsApp" subtitle={`Número del salón: ${company?.whatsapp_number || "sin configurar"} · Asistente IA Claude Sonnet 4.5`} />
      <div className="grid gap-6 lg:grid-cols-[280px_1fr_300px]">
        <Panel title="Conversaciones" testid="wa-conversations">
          <div className="mb-3 flex gap-2">
            <input className="field h-9" value={phone} onChange={(e) => setPhone(e.target.value)} data-testid="wa-phone-input" />
            <Button size="icon" variant="outline" onClick={loadMsgs} data-testid="wa-open-chat-btn"><Plus className="h-4 w-4" /></Button>
          </div>
          <ul className="max-h-[480px] space-y-1 overflow-auto">
            {convs.map((c) => (
              <li key={c.phone}>
                <button onClick={() => setPhone(c.phone)} className={`w-full rounded-lg p-2 text-left text-sm transition-colors hover:bg-secondary ${c.phone === phone ? "bg-secondary" : ""}`} data-testid={`wa-conv-${c.phone}`}>
                  <div className="font-medium">{c.name || c.phone}</div>
                  <div className="truncate text-xs text-muted-foreground">{c.last}</div>
                </button>
              </li>
            ))}
          </ul>
        </Panel>
        <div className="mx-auto flex h-[640px] w-full max-w-md flex-col overflow-hidden rounded-[2rem] border-8 border-slate-900 bg-white shadow-xl" data-testid="wa-simulator">
          <div className="flex items-center gap-3 bg-[#128C7E] px-4 py-3 text-white">
            <div className="grid h-9 w-9 place-items-center rounded-full bg-white/20"><Bot className="h-5 w-5" /></div>
            <div><div className="text-sm font-semibold">{company?.name}</div><div className="text-[11px] opacity-80">{typing ? "escribiendo..." : "Asistente IA en línea"}</div></div>
            <Phone className="ml-auto h-4 w-4 opacity-80" />
          </div>
          <div className="flex-1 space-y-2 overflow-y-auto p-3 wa-bg" data-testid="wa-messages">
            <div className="mx-auto w-fit rounded-md bg-white/80 px-2 py-0.5 text-[11px] text-slate-600">Simulando cliente {phone}</div>
            {msgs.map((m, i) => (
              <div key={m.id + i} className={`flex ${m.direction === "in" ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[80%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm shadow-sm ${m.direction === "in" ? "bg-[#DCF8C6]" : "bg-white"}`} data-testid={`wa-msg-${m.direction}`}>
                  {KIND[m.kind] && <div className="mb-0.5 text-[10px] font-semibold uppercase text-[#128C7E]">{KIND[m.kind]}</div>}
                  {m.text}
                  <div className="mt-0.5 text-right text-[10px] text-slate-500">{new Date(m.created_at).toLocaleTimeString("es-GT", { hour: "2-digit", minute: "2-digit" })}</div>
                </div>
              </div>
            ))}
            {typing && <div className="w-fit rounded-lg bg-white px-3 py-2 text-sm text-slate-500" data-testid="wa-typing">...</div>}
            <div ref={end} />
          </div>
          <div className="flex gap-1 overflow-x-auto bg-[#F0F0F0] px-2 pt-2">
            {["Hola, quiero agendar un corte mañana", "¿Qué horarios tienen el sábado?", "CONFIRMAR", "Quiero cancelar mi cita"].map((q) => (
              <button key={q} onClick={() => setText(q)} className="shrink-0 rounded-full border bg-white px-2.5 py-1 text-[11px]" data-testid="wa-quick-reply">{q}</button>
            ))}
          </div>
          <form onSubmit={send} className="flex gap-2 bg-[#F0F0F0] p-2">
            <input className="field rounded-full" placeholder="Escribe un mensaje" value={text} onChange={(e) => setText(e.target.value)} data-testid="wa-message-input" />
            <button className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-[#25D366] text-white" disabled={typing} data-testid="wa-send-btn"><Send className="h-4 w-4" /></button>
          </form>
        </div>
        <Panel title="Conectar WhatsApp real" testid="wa-connect-info">
          <div className="space-y-3 text-sm text-slate-600">
            <p className="flex gap-2"><Info className="mt-0.5 h-4 w-4 shrink-0 text-primary" />Modo SIMULADO. Los mensajes salientes se registran en la plataforma y no se envían a WhatsApp.</p>
            <p>Para producción (Meta WhatsApp Cloud API):</p>
            <ol className="list-decimal space-y-1 pl-5">
              <li>Cree una app en Meta for Developers y agregue WhatsApp.</li>
              <li>Registre el número del salón ({company?.whatsapp_number}).</li>
              <li>Configure el webhook:<div className="mt-1 break-all rounded bg-secondary p-1.5 font-mono text-[11px]">{webhook}</div></li>
              <li>Token de verificación: variable WA_VERIFY_TOKEN.</li>
              <li>Comparta el Access Token y Phone Number ID para activar el envío.</li>
            </ol>
            <p>Cada empresa se identifica por su número: el mensaje se enruta automáticamente al salón correcto.</p>
          </div>
        </Panel>
      </div>
    </div>
  );
}
