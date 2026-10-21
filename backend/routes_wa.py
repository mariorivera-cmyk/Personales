import os
import json
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Body, HTTPException, Request, Response
from emergentintegrations.llm.chat import LlmChat, UserMessage
from core import (db, find, one, uid, now_iso, today, local_now, insert, guard, wa_send, norm_phone, ALL_STAFF, valid_phone,
                  make_client_token, client_from_token, notify_company, audit)
import engine as E
import rules as R
import wa_cloud as WC
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
        "estilistas": [{"id": s["id"], "nombre": s["name"], "sucursal_id": s.get("branch_id"), "especialidades": s.get("specialties", "")} for s in stylists],
        "reglas_venta": [{"tipo": "cross-selling" if x["type"] == "cross" else "upselling", "si_reserva": names.get(x["trigger_service_id"]),
                          "sugerir_id": x["suggested_service_id"], "sugerir": names.get(x["suggested_service_id"]), "mensaje": x.get("message", "")} for x in rules],
        "cliente": {"nombre": client["name"], "puntos": client.get("points", 0),
                    "ultimo_estilista": {"id": last["stylist_id"], "nombre": last["stylist_name"], "sucursal_id": last["branch_id"],
                                         "servicio": last["service_name"], "fecha": last["date"]} if last else None}
        if client else "Cliente nuevo (pide su nombre)",
        "citas_futuras": [{"id": a["id"], "servicio": a["service_name"], "fecha": a["date"], "hora": a["time"], "estilista": a["stylist_name"],
                           "sucursal": a["branch_name"], "estado": a["status"]} for a in appts],
        "recomendaciones": [x["message"] for x in recs], "moneda": company.get("currency", "GTQ"),
        "politicas_del_salon": R.public_rules(R.effective(company)),
        "politicas_por_sucursal": {b["id"]: R.public_rules(R.effective(company, b["id"])) for b in branches},
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
7. Muestra máximo 6 horarios por mensaje. Nunca inventes precios, horarios ni políticas: usa solo politicas_del_salon (si cancel_enabled o deposit_enabled es false, no menciones esa política).
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
            slots = await E.day_slots(cid, bid, p["service_id"], p["date"], p.get("stylist_id"), public=True)
            if slots:
                return {"disponible": True, "fecha": p["date"], "sucursal_id": bid, "horarios": slots[:12]}
            return {"disponible": False, "alternativas": await E.alternatives(cid, bid, p["service_id"], p["date"], None, p.get("stylist_id"), True)}
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
                a = await E.reschedule(cid, p["appointment_id"], p["date"], p["time"], p.get("stylist_id"), by_client=True)
            else:
                a = await E.set_status(cid, p["appointment_id"], "cancelled" if t == "cancel" else "confirmed", by_client=True)
                if t == "cancel":
                    await notify_company(cid, "Cancelación por WhatsApp", f"{a['client_name']} canceló {a['service_name']} del {a['date']} {a['time']}.")
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


async def handle_inbound(to_number, phone, text, company=None, wa_id=""):
    company = company or await one("companies", {"whatsapp_number": norm_phone(to_number)})
    if not company:
        raise HTTPException(404, "Número de WhatsApp no asociado a ninguna empresa")
    cid, phone = company["id"], norm_phone(phone)
    history = await find("wa_messages", {"company_id": cid, "phone": phone}, [("created_at", -1)], 12)
    await insert("wa_messages", {"id": uid(), "company_id": cid, "phone": phone, "direction": "in", "text": text, "kind": "client", "wa_id": wa_id, "created_at": now_iso()})
    if company["status"] in ("suspended", "cancelled", "paused"):
        reply = company.get("settings", {}).get("suspension_message") or SUSPENDED_MSG
    elif "whatsapp" not in company.get("enabled_modules", []) or not company.get("setup_complete"):
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
async def meta_webhook(request: Request):
    raw = await request.body()
    if not WC.valid_signature(raw, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(401, "Firma inválida")
    try:
        body = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "JSON inválido")
    for entry in body.get("entry", []):
        for ch in entry.get("changes", []):
            v = ch.get("value", {})
            if ch.get("field") == "message_template_status_update":
                await WC.on_template_status(entry.get("id"), v)
                continue
            await WC.on_status(v)
            meta = v.get("metadata", {})
            conn = await one("wa_connections", {"phone_number_id": meta.get("phone_number_id"), "status": "connected"})
            company = await one("companies", {"id": conn["company_id"]}) if conn else None
            for msg in v.get("messages", []):
                if not msg.get("id") or await db.wa_messages.find_one({"wa_id": msg["id"]}):
                    continue
                if msg.get("type") == "text":
                    try:
                        await handle_inbound(meta.get("display_phone_number", ""), msg["from"], msg["text"]["body"], company, msg["id"])
                    except HTTPException:
                        pass
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
    if c["status"] in ("suspended", "cancelled", "paused") or "portal" not in c.get("enabled_modules", []):
        raise HTTPException(403, c.get("settings", {}).get("suspension_message") or SUSPENDED_MSG)
    if not c.get("setup_complete"):
        raise HTTPException(403, "Este salón aún está preparando su portal de reservas. Vuelva pronto.")
    return c


@r.get("/public/salon/{slug}")
async def public_salon(slug: str):
    c = await public_company(slug)
    cid = c["id"]
    s = c.get("settings", {})
    revs = await find("reviews", {"company_id": cid, "hidden": {"$ne": True}}, [("created_at", -1)], 200)
    return {"name": c["name"], "slug": slug, "whatsapp_number": c.get("whatsapp_number"), "currency": c.get("currency", "GTQ"),
            "portal": s.get("portal", {}), "waitlist": "waitlist" in c.get("enabled_modules", []),
            "description": c.get("description", ""), "logo_url": c.get("logo_url"), "photo_urls": c.get("photo_urls") or [],
            "social": c.get("social") or {}, "show_team": c.get("show_team", True), "phone": c.get("phone"),
            "rules": R.public_rules(R.effective(c)), "legal": s.get("legal", {}),
            "branch_rules": {b["id"]: R.public_rules(R.effective(c, b["id"])) for b in await find("branches", {"company_id": cid})},
            "rating": round(sum(x["rating"] for x in revs) / len(revs), 1) if revs else None, "reviews_count": len(revs),
            "reviews": [{k: x.get(k) for k in ("client_name", "rating", "comment", "service_name", "created_at")} for x in revs[:6]],
            "gallery": [{k: g.get(k) for k in ("id", "url", "caption", "service_id")} for g in await find("gallery", {"company_id": cid})],
            "branches": [{k: b.get(k) for k in ("id", "name", "address", "phone", "hours")} for b in await find("branches", {"company_id": cid})],
            "services": [{k: s.get(k) for k in ("id", "name", "description", "duration", "price", "category", "deposit", "photo_url", "price_from", "price_note")}
                         for s in await find("services", {"company_id": cid, "active": {"$ne": False}})],
            "stylists": [{k: s.get(k) for k in ("id", "name", "branch_id", "specialties", "photo")}
                         for s in await find("stylists", {"company_id": cid, "active": {"$ne": False}})]}


@r.get("/public/salon/{slug}/slots")
async def public_slots(slug: str, branch_id: str, service_id: str, date: str, stylist_id: str = ""):
    c = await public_company(slug)
    slots = await E.day_slots(c["id"], branch_id, service_id, date, stylist_id or None, public=True)
    sugg = await E.suggestions(c["id"], service_id) if "upsell" in c.get("enabled_modules", []) else []
    alts = None if slots else await E.alternatives(c["id"], branch_id, service_id, date, None, stylist_id or None, True)
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
    await wa_send(c["id"], a["client_phone"], f"¡Hola {a['client_name']}! Tu cita de {a['service_name']} está reservada para el {a['date']} a las {a['time']}."
                  f"{policy_lines(a['rules'], a['deposit_required'])}\nResponde CONFIRMAR para confirmarla.", "confirmation")
    return a


def policy_lines(ru, dep):
    pr = R.public_rules(ru)
    out = f"\n{pr['policy_text']}" if pr["cancel_enabled"] else ""
    if dep and pr["deposit_enabled"]:
        out += f"\nAnticipo requerido: Q{dep:.2f}, a enviar dentro de {ru['deposit_hours']:g} horas o la cita se libera. {pr['bank_text']} {pr['refund_text']}"
    return out


@r.post("/public/salon/{slug}/quote")
async def public_quote(slug: str, body: dict = Body(...)):
    c = await public_company(slug)
    ru = R.effective(c, body.get("branch_id") or None)
    cl = await one("clients", {"company_id": c["id"], "phone": norm_phone(body.get("phone"))}) if body.get("phone") else None
    over = bool(cl) and ru["noshow_enabled"] and await R.fault_count(cl["id"], ru) >= int(ru["noshow_limit"])
    blocked = over and ru["noshow_action"] == "block"
    dep, flagged = 0, bool(cl and cl.get("deposit_next"))
    for sid in body.get("service_ids") or []:
        svc = await one("services", {"id": sid, "company_id": c["id"]})
        if svc:
            dep += R.deposit_amount(ru, svc, int(svc["duration"]), float(svc["price"]), over, flagged)
            flagged = False
    return {"rules": R.public_rules(ru), "deposit": round(dep, 2), "blocked": blocked}


def otp_hash(code):
    return hashlib.sha256((code + os.environ["JWT_SECRET"]).encode()).hexdigest()


@r.post("/public/salon/{slug}/otp")
async def otp_request(slug: str, body: dict = Body(...)):
    c = await public_company(slug)
    phone = norm_phone(body.get("phone"))
    if not valid_phone(phone):
        raise HTTPException(400, "Teléfono inválido")
    since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    if await db.otp_codes.count_documents({"cid": c["id"], "phone": phone, "created_at": {"$gte": since}}) >= 3:
        raise HTTPException(429, "Ha solicitado demasiados códigos. Intente de nuevo en una hora")
    code = f"{secrets.randbelow(10 ** 6):06d}"
    await insert("otp_codes", {"id": uid(), "cid": c["id"], "phone": phone, "hash": otp_hash(code), "used": False,
                               "expires": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(), "created_at": now_iso()})
    if await one("clients", {"company_id": c["id"], "phone": phone}):
        await wa_send(c["id"], phone, f"Su código de verificación de {c['name']} es {code}. Vence en 10 minutos.", "otp")
    return {"message": "Te enviamos un código por WhatsApp"}


@r.post("/public/salon/{slug}/otp/verify")
async def otp_verify(slug: str, body: dict = Body(...)):
    c = await public_company(slug)
    phone = norm_phone(body.get("phone"))
    lock = await one("otp_locks", {"cid": c["id"], "phone": phone})
    if lock and lock.get("until", "") > now_iso():
        raise HTTPException(429, "Demasiados intentos. La verificación está bloqueada 15 minutos")
    rec = await db.otp_codes.find_one({"cid": c["id"], "phone": phone, "used": False}, {"_id": 0}, sort=[("created_at", -1)])
    if not rec or rec["expires"] < now_iso() or rec["hash"] != otp_hash(str(body.get("code", "")).strip()):
        cnt = ((lock or {}).get("count", 0) if not (lock or {}).get("until") else 0) + 1
        upd = {"count": cnt, "until": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat() if cnt >= 5 else ""}
        await db.otp_locks.update_one({"cid": c["id"], "phone": phone}, {"$set": upd}, upsert=True)
        raise HTTPException(400, "Código inválido o vencido")
    await db.otp_codes.update_one({"id": rec["id"]}, {"$set": {"used": True}})
    await db.otp_locks.delete_one({"cid": c["id"], "phone": phone})
    return {"token": make_client_token(c["id"], phone)}


@r.get("/public/salon/{slug}/account")
async def public_account(slug: str, request: Request):
    c = await public_company(slug)
    phone = client_from_token(request, c["id"])
    cl = await one("clients", {"company_id": c["id"], "phone": phone}) or {}
    appts = await find("appointments", {"company_id": c["id"], "client_phone": phone}, [("date", -1), ("time", -1)], 100)
    up = [a for a in appts if a["date"] >= today() and a["status"] in ("pending", "confirmed")][::-1]
    past = [a for a in appts if a["status"] == "completed"][:20]
    keys = ("id", "service_id", "service_name", "addon_names", "stylist_id", "stylist_name", "branch_id", "branch_name", "date", "time",
            "end_time", "status", "price", "deposit_required", "deposit_status")
    import packages as PK
    pks = [PK.view(x) for x in await find("client_packages", {"company_id": c["id"], "client_id": cl.get("id", "-")}, [("created_at", -1)], 30)]
    pk_keys = ("id", "name", "items", "expires", "status", "remaining", "total")
    return {"packages": [{k: x[k] for k in pk_keys} for x in pks if x["status"] in ("active", "exhausted", "expired")],
            "phone": phone, "name": cl.get("name", ""), "points": cl.get("points", 0), "membership": cl.get("membership", ""),
            "upcoming": [{k: a.get(k) for k in keys} for a in up], "past": [{k: a.get(k) for k in keys} for a in past]}


@r.post("/public/salon/{slug}/account/delete-request")
async def delete_request(slug: str, request: Request):
    c = await public_company(slug)
    phone = client_from_token(request, c["id"])
    await insert("data_requests", {"id": uid(), "company_id": c["id"], "phone": phone, "type": "delete", "status": "pending", "created_at": now_iso()})
    await notify_company(c["id"], "Solicitud de borrado de datos", f"El cliente {phone} solicitó borrar sus datos personales.")
    return {"message": "Solicitud registrada. El salón la atenderá y le confirmará por WhatsApp."}


@r.post("/public/salon/{slug}/slots-multi")
async def public_slots_multi(slug: str, body: dict = Body(...)):
    c = await public_company(slug)
    lines = body.get("lines") or []
    opts = await E.multi_slots(c["id"], body["branch_id"], body["date"], lines, public=True)
    sugg = await E.suggestions(c["id"], lines[0]["service_id"]) if lines and "upsell" in c.get("enabled_modules", []) else []
    alts = None
    if not opts and lines:
        alts = await E.alternatives(c["id"], body["branch_id"], lines[0]["service_id"], body["date"], None, lines[0].get("stylist_id") or None, True)
    return {"options": opts, "suggestions": sugg, "alternatives": alts, "today": body["date"] == today()}


@r.post("/public/salon/{slug}/book-multi")
async def public_book_multi(slug: str, body: dict = Body(...)):
    c = await public_company(slug)
    if not (body.get("name") or "").strip():
        raise HTTPException(400, "Ingrese su nombre")
    try:
        appts = await E.book_multi(c["id"], branch_id=body["branch_id"], date=body["date"], plan=body.get("plan") or [], phone=body.get("phone"),
                                   name=body["name"], email=body.get("email"), referred_by=body.get("referred_by"), source="portal",
                                   addon_ids=body.get("addon_ids"), rec_type=body.get("rec_type"))
    except E.BookingError as e:
        raise HTTPException(409, {"message": e.msg, "alternatives": e.alternatives})
    if not appts:
        raise HTTPException(400, "Seleccione al menos un servicio")
    await db.clients.update_one({"id": appts[0]["client_id"]}, {"$set": {"data_consent": now_iso()}})
    lines = "\n".join(f"- {a['service_name']}{(' + ' + ', '.join(a['addon_names'])) if a['addon_names'] else ''}: {a['time']}-{a['end_time']} con {a['stylist_name']}" for a in appts)
    dep = sum(a["deposit_required"] for a in appts)
    msg = f"¡Hola {appts[0]['client_name']}! Su reserva del {appts[0]['date']} en {appts[0]['branch_name']}:\n{lines}" + policy_lines(appts[0]["rules"], dep)
    await wa_send(c["id"], appts[0]["client_phone"], msg + "\nResponda CONFIRMAR para confirmarla.", "confirmation")
    return {"appointments": appts, "deposit_total": dep}


@r.get("/public/salon/{slug}/ics/{aid}")
async def public_ics(slug: str, aid: str, t: str):
    c = await public_company(slug)
    a = await one("appointments", {"id": aid, "company_id": c["id"], "review_token": t})
    if not a:
        raise HTTPException(404, "Cita no encontrada")
    br = await one("branches", {"id": a["branch_id"]}) or {}
    st = lambda d, h: d.replace("-", "") + "T" + h.replace(":", "") + "00"
    cancel = a["status"] == "cancelled"
    ics = "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Citalo//ES", f"METHOD:{'CANCEL' if cancel else 'PUBLISH'}", "BEGIN:VEVENT",
                       f"UID:{a['id']}@citalo", f"SEQUENCE:{len(a.get('status_log', []))}", f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
                       f"DTSTART;TZID=America/Guatemala:{st(a['date'], a['time'])}", f"DTEND;TZID=America/Guatemala:{st(a['date'], a['end_time'])}",
                       f"SUMMARY:{a['service_name']} - {c['name']}", f"LOCATION:{br.get('address') or br.get('name', '')}",
                       f"DESCRIPTION:Con {a['stylist_name']}. Tel. {br.get('phone') or c.get('phone', '')}", f"STATUS:{'CANCELLED' if cancel else 'CONFIRMED'}",
                       "END:VEVENT", "END:VCALENDAR"])
    return Response(ics, media_type="text/calendar", headers={"Content-Disposition": "attachment; filename=cita.ics"})


@r.get("/public/salon/{slug}/review/{token}")
async def review_info(slug: str, token: str):
    c = await public_company(slug)
    a = await one("appointments", {"company_id": c["id"], "review_token": token, "status": "completed"})
    if not a:
        raise HTTPException(404, "Enlace de reseña no válido")
    return {"service_name": a["service_name"], "stylist_name": a["stylist_name"], "date": a["date"],
            "reviewed": bool(await one("reviews", {"appointment_id": a["id"]}))}


@r.post("/public/salon/{slug}/review/{token}")
async def review_post(slug: str, token: str, body: dict = Body(...)):
    from routes_extra import notify_low_rating
    c = await public_company(slug)
    a = await one("appointments", {"company_id": c["id"], "review_token": token, "status": "completed"})
    if not a or await one("reviews", {"appointment_id": a["id"]}):
        raise HTTPException(400, "Esta cita ya fue calificada o el enlace no es válido")
    rating = int(body.get("rating") or 0)
    if not 1 <= rating <= 5:
        raise HTTPException(400, "Seleccione de 1 a 5 estrellas")
    rev = await insert("reviews", {"id": uid(), "company_id": c["id"], "appointment_id": a["id"], "client_name": a["client_name"].split(" ")[0],
                                   "rating": rating, "comment": (body.get("comment") or "")[:500], "service_name": a["service_name"],
                                   "stylist_name": a["stylist_name"], "hidden": False, "created_at": now_iso()})
    await notify_low_rating(c["id"], rev)
    return {"ok": True}


@r.get("/public/salon/{slug}/appointments/{aid}/cancel-preview")
async def public_cancel_preview(slug: str, aid: str, request: Request):
    c = await public_company(slug)
    phone = client_from_token(request, c["id"])
    a = await one("appointments", {"id": aid, "company_id": c["id"], "client_phone": phone})
    if not a:
        raise HTTPException(404, "Cita no encontrada")
    return E.cancel_preview(a, await E.appt_rules(a, c))


@r.get("/public/salon/{slug}/appointments/{aid}/slots")
async def public_resched_slots(slug: str, aid: str, request: Request, date: str = ""):
    c = await public_company(slug)
    phone = client_from_token(request, c["id"])
    a = await one("appointments", {"id": aid, "company_id": c["id"], "client_phone": phone})
    if not a:
        raise HTTPException(404, "Cita no encontrada")
    ru = await E.appt_rules(a, c)
    svc = await one("services", {"id": a["service_id"]})
    extra = a["duration"] - int(svc["duration"])
    count = int(a.get("reschedule_count") or 0)
    br = await one("branches", {"id": a["branch_id"]}) or {}
    info = {"reschedule_hours": ru["reschedule_hours"], "max_reschedules": ru["max_reschedules"], "count": count,
            "allowed": a["status"] in ("pending", "confirmed") and E.hours_left(a) >= float(ru["reschedule_hours"]) and count < int(ru["max_reschedules"]),
            "open_weekdays": sorted(int(k) for k in (br.get("hours") or {}).keys()),
            "min_date": (local_now() + timedelta(hours=float(ru["min_advance_hours"]))).strftime("%Y-%m-%d"),
            "max_date": (local_now() + timedelta(days=int(ru["max_advance_days"]))).strftime("%Y-%m-%d"),
            "holidays": c.get("settings", {}).get("holidays", []), "stylist_name": a["stylist_name"]}
    if not date:
        return info

    async def get(d, st):
        return await E.day_slots(c["id"], a["branch_id"], a["service_id"], d, st, exclude=aid, extra=extra, company=c, public=True)
    own = await get(date, a["stylist_id"])
    others = [] if own else [s for s in await get(date, None) if s["stylist_id"] != a["stylist_id"]]
    next_days = []
    if not own and not others:
        d0 = datetime.strptime(date, "%Y-%m-%d")
        for i in range(1, 22):
            nd = (d0 + timedelta(days=i)).strftime("%Y-%m-%d")
            if nd > info["max_date"] or len(next_days) == 3:
                break
            n = len(await get(nd, a["stylist_id"])) or len(await get(nd, None))
            if n:
                next_days.append({"date": nd, "count": n})
    return {**info, "date": date, "own": own, "others": others, "next_days": next_days}


@r.post("/public/salon/{slug}/appointments/{aid}")
async def public_manage(slug: str, aid: str, request: Request, body: dict = Body(...)):
    c = await public_company(slug)
    phone = client_from_token(request, c["id"])
    a = await one("appointments", {"id": aid, "company_id": c["id"], "client_phone": phone})
    if not a:
        raise HTTPException(404, "Cita no encontrada")
    try:
        if body.get("action") == "cancel":
            res = await E.set_status(c["id"], aid, "cancelled", reason=body.get("reason", ""), by_client=True)
            await notify_company(c["id"], "Cancelación desde el portal", f"{a['client_name']} canceló {a['service_name']} del {a['date']} {a['time']}.")
            return res
        if body.get("action") == "confirm":
            return await E.set_status(c["id"], aid, "confirmed", by_client=True)
        return await E.reschedule(c["id"], aid, body["date"], body["time"], body.get("stylist_id") or None, by_client=True)
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
    eligible = not svc or ((not svc.get("stylist_ids") or st["id"] in svc["stylist_ids"]) and (not st.get("service_ids") or svc["id"] in st["service_ids"]))
    return {"stylist_id": st["id"], "stylist_name": st["name"], "branch_id": st["branch_id"], "eligible": eligible}


@r.post("/public/salon/{slug}/waitlist")
async def public_waitlist(slug: str, body: dict = Body(...)):
    c = await public_company(slug)
    if "waitlist" not in c.get("enabled_modules", []):
        raise HTTPException(403, "Lista de espera no disponible")
    return await waitlist_entry(c["id"], body)
