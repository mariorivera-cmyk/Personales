import os
import re
import uuid
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from cryptography.fernet import Fernet
from fastapi import Request, HTTPException, Depends
from motor.motor_asyncio import AsyncIOMotorClient

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]
TZ = ZoneInfo("America/Guatemala")
FERNET = Fernet(os.environ["ENCRYPTION_KEY"].encode())
MANAGERS = ("company_admin", "branch_manager")
STAFF = ("company_admin", "branch_manager", "receptionist")
ALL_STAFF = STAFF + ("stylist",)


def uid():
    return uuid.uuid4().hex[:12]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def local_now():
    return datetime.now(TZ).replace(tzinfo=None)


def today():
    return local_now().strftime("%Y-%m-%d")


def norm_phone(p):
    d = re.sub(r"\D", "", p or "")
    return "+" + ("502" + d if len(d) == 8 else d)


def enc(text):
    return FERNET.encrypt(text.encode()).decode() if text else ""


def dec(text):
    try:
        return FERNET.decrypt(text.encode()).decode() if text else ""
    except Exception:
        return ""


def hash_pw(p):
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def check_pw(p, h):
    return bcrypt.checkpw(p.encode(), h.encode())


def make_token(user):
    payload = {"sub": user["id"], "role": user["role"], "type": "access",
               "exp": datetime.now(timezone.utc) + timedelta(hours=12)}
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm="HS256")


async def find(coll, q, sort=None, limit=5000):
    cur = db[coll].find(q, {"_id": 0})
    if sort:
        cur = cur.sort(sort)
    return await cur.to_list(limit)


async def one(coll, q):
    return await db[coll].find_one(q, {"_id": 0})


async def insert(coll, doc):
    await db[coll].insert_one(dict(doc))
    return doc


def clean(body):
    return {k: v for k, v in body.items() if k not in ("id", "company_id", "_id", "created_at", "password_hash")}


async def get_user(request: Request):
    token = request.cookies.get("access_token")
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
    if not token:
        raise HTTPException(401, "No autenticado")
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Sesión expirada")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Token inválido")
    user = await db.users.find_one({"id": payload["sub"], "active": {"$ne": False}}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(401, "Usuario no encontrado")
    return user


async def super_admin(user=Depends(get_user)):
    if user["role"] != "super_admin":
        raise HTTPException(403, "Solo Super Administrador")
    return user


async def ctx(request: Request, user=Depends(get_user)):
    cid = user.get("company_id")
    if user["role"] == "super_admin":
        cid = request.headers.get("X-Company-Id") or None
    if not cid:
        raise HTTPException(400, "Seleccione una empresa")
    company = await one("companies", {"id": cid})
    if not company:
        raise HTTPException(404, "Empresa no encontrada")
    locked = company["status"] in ("suspended_partial", "suspended", "cancelled")
    if request.method != "GET" and locked and user["role"] != "super_admin" and not request.url.path.startswith("/api/billing"):
        raise HTTPException(402, "Cuenta suspendida por falta de pago: acceso de solo lectura")
    return {"user": user, "company": company, "cid": cid}


def guard(roles=None, mod=None):
    async def dep(c: dict = Depends(ctx)):
        if roles and c["user"]["role"] != "super_admin" and c["user"]["role"] not in roles:
            raise HTTPException(403, "No tiene permisos para esta acción")
        if mod and mod not in c["company"].get("enabled_modules", []):
            raise HTTPException(403, f"El módulo '{mod}' no está habilitado para su empresa")
        return c
    return dep


async def audit(user, cid, action, entity, detail=""):
    await db.audit_logs.insert_one({
        "id": uid(), "company_id": cid, "user_id": user.get("id") if user else None,
        "user_email": user.get("email") if user else "sistema", "action": action, "entity": entity,
        "detail": str(detail)[:400], "created_at": now_iso()})


async def wa_send(cid, phone, text, kind="bot"):
    await db.wa_messages.insert_one({"id": uid(), "company_id": cid, "phone": phone, "direction": "out",
                                     "text": text, "kind": kind, "created_at": now_iso()})


def portal_url(slug, path=""):
    return f"{os.environ['FRONTEND_URL']}/b/{slug}{path}"


def make_client_token(cid, phone):
    payload = {"sub": phone, "cid": cid, "type": "client", "exp": datetime.now(timezone.utc) + timedelta(minutes=30)}
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm="HS256")


def client_from_token(request: Request, cid):
    try:
        p = jwt.decode(request.headers.get("X-Client-Token", ""), os.environ["JWT_SECRET"], algorithms=["HS256"])
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Verifique su teléfono con el código para continuar")
    if p.get("type") != "client" or p.get("cid") != cid:
        raise HTTPException(401, "Verifique su teléfono con el código para continuar")
    return p["sub"]


def valid_phone(p):
    return 8 <= len(re.sub(r"\D", "", p or "")) <= 15


def fill(tpl, **kw):
    for k, v in kw.items():
        tpl = tpl.replace("{" + k + "}", str(v))
    return tpl


async def notify_company(cid, title, text):
    await db.notifications.insert_one({"id": uid(), "company_id": cid, "title": title, "text": text, "channels": ["panel"], "created_at": now_iso()})


async def email_send(cid, to, subject, body):
    await db.email_outbox.insert_one({"id": uid(), "company_id": cid, "to": to, "subject": subject,
                                      "body": body, "created_at": now_iso()})
