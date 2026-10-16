import os
import json
from fastapi import APIRouter, Depends, Body, HTTPException, Request, Response
from emergentintegrations.llm.chat import LlmChat, UserMessage
from core import db, find, one, uid, now_iso, today, local_now, insert, guard, wa_send, norm_phone, ALL_STAFF
import engine as E
from routes_ops import waitlist_entry

r = APIRouter(prefix="/api")
MODEL = ("anthropic", "claude-sonnet-4-5-20250929")
SUSPENDED_MSG = "Por el momento nuestro sistema de reservas no está disponible. Por favor comuníquese directamente con el salón."


async def context_for(company, phone):
    cid = company["id"]
    services = await find("services", {"company_id": cid, "active": {"$ne": False}})
    branches = await find("branches", {"company_id": cid})
    stylists = await find("stylists", {"company_id": cid, "active": {"$ne": False}})
    rules = await find("upsell_rules", {"company_id": cid, "active": {"$ne": False}}) if "upsell" in company.get("enabled_modules", []) else []
    client = await one("clients", {"company_id": cid, "phone": phone})
    appts = await find("appointments", {"company_id": cid, "client_phone": phone, "date": {"$gte": today()},
                                        "status": {"$in": ["pending", "confirmed"]}}) if client else []
    recs = await E.recommendations(cid, client["id"]) if client else []
    last = await db.appointments.find_one({"company_id": cid, "client_phone": phone, "status": "completed"}, {"_id": 0},
                                          sort=[("date", -1), ("time", -1)]) if client else None
    names = {s["id"]: s["name"] for s in services}
    return {
        "salon": company["name"], "hoy": f"{today()} ({local_now().strftime('%A %H:%M')})",
        "servicios": [{"id": s["id"], "nombre": s["name"], "duracion_min": s["duration"], "precio": s["price"],
                       "categoria": s.get("category", "")} for s in services],
        "sucursales": [{"id": b["id"], "nombre": b["name"], "direccion": b.get("address", "")} for b in branches],
        "estilistas": [{"id": s["id"], "nombre": s["name"], "sucursal_id": s["branch_id"], "especialidades": s.get("specialties", "")} for s in stylists],
        "reglas_venta": [{"tipo": "cross-selling" if x["type"] == "cross" else "upselling", "si_reserva": names.get(x["trigger_service_id"]),
                          "sugerir_id": x["suggested_service_id"], "sugerir": names.get(x["suggested_service_id"]), "mensaje": x.get("message", "")} for x in rules],
        "cliente": {"nombre": client["name"], "puntos": client.get("points", 0),
                    "ultimo_estilista": {"id": last["stylist_id"], "nombre": last["stylist_name"], "sucursal_id": last["branch_id"],
                                         "servicio": last["service_name"], "fecha": last["date"]} if last else None}
        if client else "Cliente nuevo (pide su nombre)",
        "citas_futuras": [{"id": a["id"], "servicio": a["service_name"], "fecha": a["date"], "hora": a["time"], "estilista": a["stylist_name"],
                           "sucursal": a["branch_name"], "estado": a["status"]} for a in appts],
        "recomendaciones": [x["message"] for x in recs], "moneda": company.get("currency", "GTQ"),
    }


SYSTEM = """Eres el asistente virtual de WhatsApp del salón de belleza "{salon}". Hablas español, eres cálido, breve y profesional (máximo 1 emoji por mensaje).
Puedes: consultar disponibilidad, reservar, reprogramar, cancelar y confirmar citas, inscribir en lista de espera y actualizar el nombre del cliente.
DATOS DEL NEGOCIO (JSON): {data}

RESPONDE SIEMPRE ÚNICAMENTE con un objeto JSON válido, sin texto fuera del JSON:
{{"reply": "mensaje para el cliente", "action": {{"type": "none"}}}}
Tipos de action y parámetros:
- availability: service_id, date (YYYY-MM-DD), branch_id (opcional), stylist_id (opcional)
- book: service_id, date, time (HH:MM), branch_id, stylist_id (opcional), addon_ids (lista opcional), rec_type ("cross"|"up" si el cliente aceptó una sugerencia), name (opcional)
- reschedule: appointment_id, date, time, stylist_id (opcional)
- cancel: appointment_id
- confirm: appointment_id
- waitlist: service_id, date, branch_id
- set_name: name
- none
Reglas:
1. Usa sólo IDs presentes en los datos. Interpreta "mañana", "el viernes", etc. con base en la fecha de hoy.
2. Antes de reservar SIEMPRE consulta disponibilidad (availability) salvo que ya tengas el resultado para esa fecha.
3. Cuando ejecutes una acción distinta de none, deja "reply" vacío; el sistema te enviará RESULTADO_SISTEMA y entonces redactas la respuesta final con action none.
4. Si no hay disponibilidad, ofrece las alternativas recibidas (otros horarios, otros estilistas, otras sucursales) o la lista de espera.
5. Antes de confirmar una reserva, si hay reglas_venta para ese servicio, sugiere UNA vez el servicio complementario o premium.
6. Si el cliente responde CONFIRMAR, REPROGRAMAR o CANCELAR a un recordatorio, actúa sobre su cita futura más próxima.
7. Muestra máximo 6 horarios por mensaje. Nunca inventes precios ni horarios.
8. Antes de consultar disponibilidad para una NUEVA cita, pregunta SIEMPRE al cliente si tiene un estilista de preferencia (menciona los estilistas de la sucursal que hacen ese servicio) o si prefiere que le asignemos a alguien según disponibilidad. Si elige un estilista, usa su stylist_id en availability y book; si prefiere asignación, omite stylist_id y usa el estilista que devuelva el horario elegido. Si el cliente ya lo indicó en su mensaje, no vuelvas a preguntar.
9. Si el cliente tiene ultimo_estilista y ese estilista está en la sucursal y realiza el servicio solicitado, propónlo PRIMERO por su nombre (ej. "¿Desea agendar nuevamente con Carla, quien le atendió la última vez?") y ofrece como alternativa elegir otro estilista o la asignación según disponibilidad. Si no realiza ese servicio o no está en esa sucursal, aplica la regla 8 normalmente."""


def parse(text):
    try:
        return json.loads(text[text.index("{"): text.rindex("}") + 1])
    except Exception:
        return {"reply": text.strip(), "action": {"type": "none"}}


async def execute(company, phone, action):
    cid, t, p = company["id"], action.get("type"), action
    branches = await find("branches", {"company_id": cid})
    bid = p.get("branch_id") or (branches[0]["id"] if branches else None)
    mine = lambda aid: one("appointments", {"id": aid, "company_id": cid, "client_phone": phone})
    try:
        if t == "availability":
            slots = await E.day_slots(cid, bid, p["service_id"], p["date"], p.get("stylist_id"))
            if slots:
                return {"disponible": True, "fecha": p["date"], "sucursal_id": bid, "horarios": slots[:12]}
            return {"disponible": False, "alternativas": await E.alternatives(cid, bid, p["service_id"], p["date"], None, p.get("stylist_id"))}
        if t == "book":
            a = await E.book(cid, branch_id=bid, service_id=p["service_id"], date=p["date"], time=p["time"], phone=phone,
                             name=p.get("name"), stylist_id=p.get("stylist_id"), addon_ids=p.get("addon_ids"),
                             rec_type=p.get("rec_type"), source="whatsapp")
            return {"ok": True, "cita": {k: a[k] for k in ("id", "service_name", "addon_names", "date", "time", "stylist_name",
                                                            "branch_name", "price", "deposit_required")}}
        if t in ("reschedule", "cancel", "confirm"):
            if not await mine(p.get("appointment_id")):
                return {"ok": False, "error": "Cita no encontrada para este cliente"}
            if t == "reschedule":
                a = await E.reschedule(cid, p["appointment_id"], p["date"], p["time"], p.get("stylist_id"))
            else:
                a = await E.set_status(cid, p["appointment_id"], "cancelled" if t == "cancel" else "confirmed")
            return {"ok": True, "cita": {k: a[k] for k in ("id", "service_name", "date", "time", "stylist_name", "status")}}
        if t == "waitlist":
            if "waitlist" not in company.get("enabled_modules", []):
                return {"ok": False, "error": "Lista de espera no disponible"}
            w = await waitlist_entry(cid, {"phone": phone, "service_id": p.get("service_id"), "branch_id": bid, "date": p.get("date")})
            return {"ok": True, "lista_espera": w["id"]}
        if t == "set_name":
            await E.upsert_client(cid, phone, p.get("name"))
            await db.clients.update_one({"company_id": cid, "phone": phone}, {"$set": {"name": p.get("name")}})
            return {"ok": True}
    except E.BookingError as e:
        return {"ok": False, "error": e.msg, "alternativas": e.alternatives}
    except KeyError as e:
        return {"ok": False, "error": f"Falta parámetro {e}"}
    return {"ok": False, "error": "Acción desconocida"}


async def handle_inbound(to_number, phone, text):
    company = await one("companies", {"whatsapp_number": norm_phone(to_number)})
    if not company:
        raise HTTPException(404, "Número de WhatsApp no asociado a ninguna empresa")
    cid, phone = company["id"], norm_phone(phone)
    history = await find("wa_messages", {"company_id": cid, "phone": phone}, [("created_at", -1)], 12)
    await insert("wa_messages", {"id": uid(), "company_id": cid, "phone": phone, "direction": "in", "text": text, "kind": "client", "created_at": now_iso()})
    if company["status"] in ("suspended", "cancelled"):
        reply = company.get("settings", {}).get("suspension_message") or SUSPENDED_MSG
    elif "whatsapp" not in company.get("enabled_modules", []):
        reply = "Gracias por escribirnos. Un asesor le atenderá pronto."
    else:
        reply = await bot_reply(company, phone, text, history[::-1])
    await wa_send(cid, phone, reply, "bot")
    return {"reply": reply}


async def bot_reply(company, phone, text, history):
    data = await context_for(company, phone)
    chat = LlmChat(api_key=os.environ["EMERGENT_LLM_KEY"], session_id=f"wa-{company['id']}-{phone}-{uid()}",
                   system_message=SYSTEM.format(salon=company["name"], data=json.dumps(data, ensure_ascii=False))).with_model(*MODEL)
    transcript = "\n".join(f"{'Cliente' if h['direction'] == 'in' else 'Salón'}: {h['text']}" for h in history)
    msg = f"Historial reciente:\n{transcript or '(sin mensajes)'}\n\nNuevo mensaje del cliente: {text}"
    try:
        for _ in range(4):
            out = parse(await chat.send_message(UserMessage(text=msg)))
            action = out.get("action") or {"type": "none"}
            if action.get("type", "none") == "none":
                return out.get("reply") or "¿En qué más le puedo ayudar?"
            result = await execute(company, phone, action)
            msg = "RESULTADO_SISTEMA: " + json.dumps(result, ensure_ascii=False)
        return out.get("reply") or "Disculpe, ¿podría repetir su solicitud?"
    except Exception:
        return "Disculpe, tuvimos un inconveniente técnico. Intente de nuevo en un momento."


@r.post("/wa/inbound")
async def inbound(body: dict = Body(...)):
    if not body.get("from_phone") or not body.get("text"):
        raise HTTPException(400, "from_phone y text son requeridos")
    return await handle_inbound(body.get("to", ""), body["from_phone"], body["text"])


@r.get("/wa/webhook")
async def meta_verify(request: Request):
    q = request.query_params
    if q.get("hub.verify_token") == os.environ.get("WA_VERIFY_TOKEN"):
        return Response(q.get("hub.challenge", ""))
    raise HTTPException(403, "Token inválido")


@r.post("/wa/webhook")
async def meta_webhook(body: dict = Body(...)):
    for entry in body.get("entry", []):
        for ch in entry.get("changes", []):
            v = ch.get("value", {})
            to = v.get("metadata", {}).get("display_phone_number", "")
            for msg in v.get("messages", []):
                if msg.get("type") == "text":
                    await handle_inbound(to, msg["from"], msg["text"]["body"])
    return {"ok": True}


@r.get("/wa/conversations")
async def conversations(c=Depends(guard(ALL_STAFF))):
    pipe = [{"$match": {"company_id": c["cid"]}}, {"$sort": {"created_at": -1}},
            {"$group": {"_id": "$phone", "last": {"$first": "$text"}, "at": {"$first": "$created_at"}, "count": {"$sum": 1}}},
            {"$sort": {"at": -1}}, {"$limit": 100}]
    rows = await db.wa_messages.aggregate(pipe).to_list(100)
    names = {x["phone"]: x["name"] for x in await find("clients", {"company_id": c["cid"]})}
    return [{"phone": x["_id"], "name": names.get(x["_id"], ""), "last": x["last"], "at": x["at"], "count": x["count"]} for x in rows]


@r.get("/wa/messages")
async def messages(phone: str, c=Depends(guard(ALL_STAFF))):
    return await find("wa_messages", {"company_id": c["cid"], "phone": norm_phone(phone)}, [("created_at", 1)], 300)


# ---------- Public booking portal ----------
async def public_company(slug):
    c = await one("companies", {"slug": slug})
    if not c:
        raise HTTPException(404, "Salón no encontrado")
    if c["status"] in ("suspended", "cancelled") or "portal" not in c.get("enabled_modules", []):
        raise HTTPException(403, c.get("settings", {}).get("suspension_message") or SUSPENDED_MSG)
    return c


@r.get("/public/salon/{slug}")
async def public_salon(slug: str):
    c = await public_company(slug)
    cid = c["id"]
    return {"name": c["name"], "slug": slug, "whatsapp_number": c.get("whatsapp_number"), "currency": c.get("currency", "GTQ"),
            "portal": c.get("settings", {}).get("portal", {}), "waitlist": "waitlist" in c.get("enabled_modules", []),
            "branches": [{k: b.get(k) for k in ("id", "name", "address", "phone")} for b in await find("branches", {"company_id": cid})],
            "services": [{k: s.get(k) for k in ("id", "name", "description", "duration", "price", "category", "deposit")}
                         for s in await find("services", {"company_id": cid, "active": {"$ne": False}})],
            "stylists": [{k: s.get(k) for k in ("id", "name", "branch_id", "specialties", "photo")}
                         for s in await find("stylists", {"company_id": cid, "active": {"$ne": False}})]}


@r.get("/public/salon/{slug}/slots")
async def public_slots(slug: str, branch_id: str, service_id: str, date: str, stylist_id: str = ""):
    c = await public_company(slug)
    slots = await E.day_slots(c["id"], branch_id, service_id, date, stylist_id or None)
    sugg = await E.suggestions(c["id"], service_id) if "upsell" in c.get("enabled_modules", []) else []
    alts = None if slots else await E.alternatives(c["id"], branch_id, service_id, date, None, stylist_id or None)
    return {"slots": slots, "alternatives": alts, "suggestions": sugg}


@r.post("/public/salon/{slug}/book")
async def public_book(slug: str, body: dict = Body(...)):
    c = await public_company(slug)
    if not body.get("phone") or not body.get("name"):
        raise HTTPException(400, "Nombre y teléfono son requeridos")
    try:
        a = await E.book(c["id"], branch_id=body["branch_id"], service_id=body["service_id"], date=body["date"], time=body["time"],
                         phone=body["phone"], name=body["name"], email=body.get("email"), stylist_id=body.get("stylist_id") or None,
                         addon_ids=body.get("addon_ids"), rec_type=body.get("rec_type"), source="portal",
                         referred_by=body.get("referred_by"))
    except E.BookingError as e:
        raise HTTPException(409, {"message": e.msg, "alternatives": e.alternatives})
    await wa_send(c["id"], a["client_phone"], f"¡Hola {a['client_name']}! Tu cita de {a['service_name']} está reservada para el {a['date']} a las {a['time']}. Responde CONFIRMAR para confirmarla.", "confirmation")
    return a


@r.post("/public/salon/{slug}/my")
async def public_my(slug: str, body: dict = Body(...)):
    c = await public_company(slug)
    return await find("appointments", {"company_id": c["id"], "client_phone": norm_phone(body.get("phone")), "date": {"$gte": today()},
                                       "status": {"$in": ["pending", "confirmed"]}}, [("date", 1)])


@r.post("/public/salon/{slug}/appointments/{aid}")
async def public_manage(slug: str, aid: str, body: dict = Body(...)):
    c = await public_company(slug)
    a = await one("appointments", {"id": aid, "company_id": c["id"], "client_phone": norm_phone(body.get("phone"))})
    if not a:
        raise HTTPException(404, "Cita no encontrada")
    try:
        if body.get("action") == "cancel":
            return await E.set_status(c["id"], aid, "cancelled")
        if body.get("action") == "confirm":
            return await E.set_status(c["id"], aid, "confirmed")
        return await E.reschedule(c["id"], aid, body["date"], body["time"], body.get("stylist_id") or None)
    except E.BookingError as e:
        raise HTTPException(409, {"message": e.msg, "alternatives": e.alternatives})


@r.post("/public/salon/{slug}/last-stylist")
async def public_last_stylist(slug: str, body: dict = Body(...)):
    c = await public_company(slug)
    last = await db.appointments.find_one({"company_id": c["id"], "client_phone": norm_phone(body.get("phone")), "status": "completed"},
                                          {"_id": 0}, sort=[("date", -1), ("time", -1)])
    if not last:
        return None
    st = await one("stylists", {"id": last["stylist_id"], "company_id": c["id"], "active": {"$ne": False}})
    if not st:
        return None
    svc = await one("services", {"id": body.get("service_id"), "company_id": c["id"]}) if body.get("service_id") else None
    eligible = not svc or not svc.get("stylist_ids") or st["id"] in svc["stylist_ids"]
    return {"stylist_id": st["id"], "stylist_name": st["name"], "branch_id": st["branch_id"], "eligible": eligible}


@r.post("/public/salon/{slug}/waitlist")
async def public_waitlist(slug: str, body: dict = Body(...)):
    c = await public_company(slug)
    if "waitlist" not in c.get("enabled_modules", []):
        raise HTTPException(403, "Lista de espera no disponible")
    return await waitlist_entry(c["id"], body)
