import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { toast } from "sonner";
import { Star } from "lucide-react";
import { api, errMsg } from "@/lib/api";
import { Button } from "@/components/ui/button";

export default function ReviewPage() {
  const { slug, token } = useParams();
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const [sent, setSent] = useState(false);
  useEffect(() => { api.get(`/public/salon/${slug}/review/${token}`).then((r) => setD(r.data)).catch((e) => setErr(errMsg(e))); }, [slug, token]);
  const send = async () => {
    try { await api.post(`/public/salon/${slug}/review/${token}`, { rating, comment }); setSent(true); } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div className="grid min-h-screen place-items-center p-6" data-testid="review-page">
      <div className="w-full max-w-md rounded-3xl border bg-white p-8 text-center">
        {err ? <p>{err}</p> : !d ? null : sent || d.reviewed ? <p className="font-heading text-xl" data-testid="review-thanks">¡Gracias por su opinión!</p> : (<>
          <h1 className="font-heading text-2xl font-bold">¿Cómo le fue?</h1>
          <p className="mt-1 text-sm text-muted-foreground">{d.service_name} con {d.stylist_name} · {d.date}</p>
          <div className="my-5 flex justify-center gap-2">{[1, 2, 3, 4, 5].map((n) => (
            <button key={n} onClick={() => setRating(n)} data-testid={`star-${n}`}><Star className={`h-9 w-9 ${n <= rating ? "fill-amber-400 text-amber-400" : "text-slate-300"}`} /></button>
          ))}</div>
          <textarea className="field h-24 py-2" placeholder="Comentario (opcional)" value={comment} onChange={(e) => setComment(e.target.value)} data-testid="review-comment" />
          <Button className="mt-4 w-full rounded-full" disabled={!rating} onClick={send} data-testid="review-submit">Enviar</Button>
        </>)}
      </div>
    </div>
  );
}
