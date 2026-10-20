import os
import re
import hmac
import hashlib
from datetime import datetime, timezone, timedelta
import httpx
from fastapi import APIRouter, Depends, Body, HTTPException
from core import db, one, enc, dec, now_iso, norm_phone, guard, audit

r = APIRouter(prefix="/api")
OWNER = ("company_admin",)
EX = "Salón Bella Vida"

TEMPLATES = [
    {"name": "salonflow_confirmacion", "category": "UTILITY", "label": "Confirmación de cita", "kinds": ["confirmation"],
     "body": "Confirmación de su cita en {{1}}: {{2}}", "example": "su cita de Corte quedó para el 2026-03-10 a las 10:00."},
    {"name": "salonflow_recordatorio", "category": "UTILITY", "label": "Recordatorio de cita", "kinds": ["reminder"],
     "body": "Recordatorio de {{1}}: {{2}}", "example": "su cita de Corte es mañana a las 10:00. Responda CONFIRMAR."},
    {"name": "salonflow_cambio_cita", "category": "UTILITY", "label": "Cita reprogramada / espacio liberado", "kinds": ["reschedule", "waitlist", "bot"],
     "body": "Actualización de su cita en {{1}}: {{2}}", "example": "su cita fue movida al 2026-03-11 a las 15:00."},
    {"name": "salonflow_cancelacion", "category": "UTILITY", "label": "Cita cancelada", "kinds": ["cancellation", "policy"],
     "body": "Aviso de {{1}} sobre su cita: {{2}}", "example": "su cita de Corte del 2026-03-10 fue cancelada."},
    {"name": "salonflow_codigo", "category": "AUTHENTICATION", "label": "Código de acceso a Mis citas", "kinds": ["otp"]},
    {"name": "salonflow_anticipo", "category": "UTILITY", "label": "Anticipo pendiente", "kinds": ["deposit"],
     "body": "Anticipo de su cita en {{1}}: {{2}}", "example": "recuerde enviar su anticipo de Q50.00 antes de las 18:00."},
    {"name": "salonflow_resena", "category": "UTILITY", "label": "Solicitud de reseña", "kinds": ["review"],
     "body": "Gracias por visitar {{1}}. {{2}}", "example": "¿Cómo fue su experiencia? Califíquenos aquí: https://ejemplo.com/r"},
    {"name": "salonflow_promocion", "category": "MARKETING", "label": "Promociones y cumpleaños", "kinds": ["campaign"],
     "body": "Novedades de {{1}}: {{2}}", "example": "este mes 20% de descuento en tintes.", "footer": "Responda BAJA para no recibir promociones"},
]
BY_KIND = {k: t["name"] for t in TEMPLATES for k in t["kinds"]}


def enabled():
    return all(os.environ.get(k) for k in ("META_APP_ID", "META_APP_SECRET", "META_CONFIG_ID"))


def base():
    return f"https://graph.facebook.com/{os.environ['META_GRAPH_VERSION']}"


async def graph(method, path, token, body=None, params=None):
    proof = hmac.new(os.environ["META_APP_SECRET"].encode(), token.encode(), hashlib.sha256).hexdigest()
    async with httpx.AsyncClient(timeout=30) as h:
        res = await h.request(method, base() + path, json=body, params={**(params or {}), "appsecret_proof": proof},
                              headers={"Authorization": f"Bearer {token}"})
    data = res.json() if res.content else {}
    if res.status_code >= 400:
        raise HTTPException(400, "Meta: " + (data.get("error", {}).get("error_user_msg") or data.get("error", {}).get("message") or "error"))
    return data


def template_payload(t):
    if t["category"] == "AUTHENTICATION":
        comps = [{"type": "BODY", "add_security_recommendation": True}, {"type": "FOOTER", "code_expiration_minutes": 10},
                 {"type": "BUTTONS", "buttons": [{"type": "OTP", "otp_type": "COPY_CODE", "text": "Copiar código"}]}]
    else:
        comps = [{"type": "BODY", "text": t["body"], "example": {"body_text": [[EX, t["example"]]]}}]
        if t.get("footer"):
            comps.append({"type": "FOOTER", "text": t["footer"]})
    return {"name": t["name"], "language": "es", "category": t["category"], "components": comps}


async def create_templates(conn, token):
    out = dict(conn.get("templates") or {})
    for t in TEMPLATES:
        if out.get(t["name"], {}).get("status") in ("APPROVED", "PENDING"):
            continue
        try:
            res = await graph("POST", f"/{conn['waba_id']}/message_templates", token, template_payload(t))
            out[t["name"]] = {"status": res.get("status", "PENDING"), "reason": ""}
        except HTTPException as e:
            out[t["name"]] = {"status": "ERROR", "reason": e.detail}
    return out


async def sync_templates(conn, token):
    res = await graph("GET", f"/{conn['waba_id']}/message_templates", token, params={"fields": "name,status,rejected_reason", "limit": 200})
    out = dict(conn.get("templates") or {})
    for x in res.get("data", []):
        if x.get("name") in BY_KIND.values():
            out[x["name"]] = {"status": x.get("status", ""), "reason": x.get("rejected_reason") or ""}
    return out


def public_conn(conn):
    if not conn:
        return None
    return {k: conn.get(k) for k in ("status", "display_phone_number", "verified_name", "waba_id", "phone_number_id", "connected_at")}


@r.get("/wa-cloud/status")
async def status(c=Depends(guard(OWNER))):
    conn = await one("wa_connections", {"company_id": c["cid"]})
    tpl = (conn or {}).get("templates") or {}
    return {"enabled": enabled(), "app_id": os.environ.get("META_APP_ID") if enabled() else None,
            "config_id": os.environ.get("META_CONFIG_ID") if enabled() else None,
            "graph_version": os.environ["META_GRAPH_VERSION"], "connection": public_conn(conn),
            "templates": [{"name": t["name"], "label": t["label"], "category": t["category"], **tpl.get(t["name"], {"status": "NOT_CREATED", "reason": ""})}
                          for t in TEMPLATES]}


@r.post("/wa-cloud/connect")
async def connect(c=Depends(guard(OWNER)), body: dict = Body(...)):
    if not enabled():
        raise HTTPException(503, "La conexión con WhatsApp está pendiente de configuración por la plataforma")
    code, waba = (body.get("code") or "").strip(), (body.get("waba_id") or "").strip()
    pin = (body.get("pin") or "").strip()
    if not code or not waba:
        raise HTTPException(400, "Meta no devolvió los datos de la cuenta. Intente conectar de nuevo.")
    if pin and not re.fullmatch(r"\d{6}", pin):
        raise HTTPException(400, "El PIN debe tener 6 dígitos")
    async with httpx.AsyncClient(timeout=30) as h:
        res = await h.get(f"{base()}/oauth/access_token", params={"client_id": os.environ["META_APP_ID"],
                                                                  "client_secret": os.environ["META_APP_SECRET"], "code": code})
    if res.status_code >= 400 or "access_token" not in res.json():
        raise HTTPException(400, "Meta rechazó la autorización. Vuelva a intentar la conexión.")
    token = res.json()["access_token"]
    phone_id = (body.get("phone_number_id") or "").strip()
    if not phone_id:
        phones = (await graph("GET", f"/{waba}/phone_numbers", token)).get("data") or []
        phone_id = phones[0]["id"] if phones else ""
    if not phone_id:
        raise HTTPException(400, "La cuenta de WhatsApp no tiene un número registrado")
    other = await one("wa_connections", {"phone_number_id": phone_id, "company_id": {"$ne": c["cid"]}, "status": "connected"})
    if other:
        raise HTTPException(409, "Este número ya está conectado a otro salón")
    info = await graph("GET", f"/{phone_id}", token, params={"fields": "display_phone_number,verified_name"})
    if pin:
        await graph("POST", f"/{phone_id}/register", token, {"messaging_product": "whatsapp", "pin": pin})
    await graph("POST", f"/{waba}/subscribed_apps", token)
    conn = {"company_id": c["cid"], "status": "connected", "waba_id": waba, "phone_number_id": phone_id,
            "display_phone_number": info.get("display_phone_number", ""), "verified_name": info.get("verified_name", ""),
            "token": enc(token), "connected_at": now_iso(), "templates": {}}
    conn["templates"] = await create_templates(conn, token)
    await db.wa_connections.update_one({"company_id": c["cid"]}, {"$set": conn}, upsert=True)
    if conn["display_phone_number"]:
        await db.companies.update_one({"id": c["cid"]}, {"$set": {"whatsapp_number": norm_phone(conn["display_phone_number"])}})
    await audit(c["user"], c["cid"], "whatsapp_connect", "wa_connection", conn["display_phone_number"])
    return await status(c)


@r.post("/wa-cloud/templates/sync")
async def templates_sync(c=Depends(guard(OWNER))):
    conn = await one("wa_connections", {"company_id": c["cid"], "status": "connected"})
    if not conn or not enabled():
        raise HTTPException(409, "WhatsApp no está conectado")
    token = dec(conn["token"])
    conn["templates"] = await sync_templates(conn, token)
    conn["templates"] = await create_templates(conn, token)
    await db.wa_connections.update_one({"company_id": c["cid"]}, {"$set": {"templates": conn["templates"]}})
    return await status(c)


@r.post("/wa-cloud/disconnect")
async def disconnect(c=Depends(guard(OWNER))):
    conn = await one("wa_connections", {"company_id": c["cid"]})
    if not conn:
        raise HTTPException(409, "WhatsApp no está conectado")
    await db.wa_connections.update_one({"company_id": c["cid"]}, {"$set": {"status": "disconnected", "token": "", "disconnected_at": now_iso()}})
    await audit(c["user"], c["cid"], "whatsapp_disconnect", "wa_connection", conn.get("display_phone_number", ""))
    return await status(c)


def otp_code(text):
    m = re.search(r"\b(\d{4,8})\b", text)
    return m.group(1) if m else ""


async def deliver(cid, phone, text, kind):
    conn = await one("wa_connections", {"company_id": cid, "status": "connected"})
    if not conn or not enabled():
        return {"delivery": "simulated"}
    company = await one("companies", {"id": cid})
    since = (datetime.now(timezone.utc) - timedelta(hours=23, minutes=50)).isoformat()
    in_window = await db.wa_messages.find_one({"company_id": cid, "phone": phone, "direction": "in", "created_at": {"$gte": since}})
    payload = {"messaging_product": "whatsapp", "to": re.sub(r"\D", "", phone)}
    if in_window and kind != "otp":
        payload.update(type="text", text={"body": text[:4096]})
    else:
        name = BY_KIND.get(kind, "salonflow_cambio_cita")
        if (conn.get("templates") or {}).get(name, {}).get("status") != "APPROVED":
            return {"delivery": "failed", "delivery_error": "La plantilla aún no está aprobada por Meta"}
        if kind == "otp":
            code = otp_code(text)
            comps = [{"type": "body", "parameters": [{"type": "text", "text": code}]},
                     {"type": "button", "sub_type": "url", "index": "0", "parameters": [{"type": "text", "text": code}]}]
        else:
            flat = re.sub(r"\s+", " ", text).strip()[:900]
            comps = [{"type": "body", "parameters": [{"type": "text", "text": company["name"]}, {"type": "text", "text": flat}]}]
        payload.update(type="template", template={"name": name, "language": {"code": "es"}, "components": comps})
    try:
        res = await graph("POST", f"/{conn['phone_number_id']}/messages", dec(conn["token"]), payload)
        return {"delivery": "sent", "wa_id": (res.get("messages") or [{}])[0].get("id", "")}
    except Exception as e:
        return {"delivery": "failed", "delivery_error": str(getattr(e, "detail", e))[:300]}


def valid_signature(raw, header):
    secret = os.environ.get("META_APP_SECRET")
    if not secret:
        return True
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(header or "", expected)


async def on_template_status(waba_id, value):
    name = value.get("message_template_name")
    if name in BY_KIND.values():
        await db.wa_connections.update_one({"waba_id": waba_id}, {"$set": {f"templates.{name}": {
            "status": value.get("event", ""), "reason": value.get("reason") or ""}}})


async def on_status(value):
    for s in value.get("statuses", []):
        await db.wa_messages.update_one({"wa_id": s.get("id")}, {"$set": {"delivery": s.get("status", "")}})
