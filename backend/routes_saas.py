import io
import os
import re
import hmac
import asyncio
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Body, HTTPException, Response, Request
from core import db, find, one, uid, now_iso, today, insert, clean, audit, hash_pw, check_pw, make_token, get_user, super_admin, guard, ctx
from billing import (DEFAULT_SETTINGS, psettings, breakdown, monthly_value, create_invoice, charge, mark_paid, prorate_module,
                     statement, invoice_pdf, cycle_items, METHODS, account_statement, account_statement_pdf,
                     advance_preview, advance_charge)

r = APIRouter(prefix="/api")
BLOCKED = {"paused": "La cuenta de su empresa está en pausa. Comuníquese con soporte de SalonFlow.",
           "cancelled": "La cuenta de su empresa fue cancelada. Comuníquese con soporte de SalonFlow si desea reactivarla."}
STATUS_LABEL = {"trial": "Prueba (30 días)", "active": "Activa", "paused": "En pausa", "cancelled": "Cancelada"}
TASKS = set()


@r.post("/auth/login")
async def login(response: Response, body: dict = Body(...)):
    email = (body.get("email") or "").strip().lower()
    ident = f"login:{email}"
    att = await one("login_attempts", {"identifier": ident})
    if att and att.get("count", 0) >= 5 and att.get("until", "") > now_iso():
        raise HTTPException(429, "Demasiados intentos. Intente en 15 minutos")
    u = await db.users.find_one({"email": email, "active": {"$ne": False}}, {"_id": 0})
    if not u or not check_pw(body.get("password") or "", u["password_hash"]):
        cnt = (att or {}).get("count", 0) + 1
        await db.login_attempts.update_one({"identifier": ident}, {"$set": {"count": cnt, "until": (datetime.utcnow() + timedelta(minutes=15)).isoformat()}}, upsert=True)
        raise HTTPException(401, "Correo o contraseña incorrectos")
    await db.login_attempts.delete_one({"identifier": ident})
    if u["role"] != "super_admin" and u.get("company_id"):
        co = await one("companies", {"id": u["company_id"]})
        if co and co["status"] in BLOCKED:
            raise HTTPException(403, BLOCKED[co["status"]])
    u.pop("password_hash")
    token = make_token(u)
    response.set_cookie("access_token", token, httponly=True, secure=True, samesite="none", max_age=43200, path="/")
    await audit(u, u.get("company_id"), "login", "auth", email)
    return {"token": token, "user": u}


@r.get("/auth/me")
async def me(user=Depends(get_user)):
    company = await one("companies", {"id": user.get("company_id")}) if user.get("company_id") else None
    if company and user["role"] != "super_admin" and company["status"] in BLOCKED:
        raise HTTPException(403, BLOCKED[company["status"]])
    return {"user": user, "company": company}


@r.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


def admin_crud(name, coll):
    @r.get(f"/admin/{name}", name=f"admin_list_{name}")
    async def _list(u=Depends(super_admin)):
        return await find(coll, {}, [("created_at", 1)])

    @r.post(f"/admin/{name}", name=f"admin_create_{name}")
    async def _create(body: dict = Body(...), u=Depends(super_admin)):
        doc = {**clean(body), "id": uid(), "created_at": now_iso()}
        await audit(u, None, "create", name, doc.get("name", ""))
        return await insert(coll, doc)

    @r.put(f"/admin/{name}/{{oid}}", name=f"admin_update_{name}")
    async def _update(oid: str, body: dict = Body(...), u=Depends(super_admin)):
        await db[coll].update_one({"id": oid}, {"$set": clean(body)})
        await audit(u, None, "update", name, oid)
        return await one(coll, {"id": oid})

    @r.delete(f"/admin/{name}/{{oid}}", name=f"admin_delete_{name}")
    async def _delete(oid: str, u=Depends(super_admin)):
        await db[coll].delete_one({"id": oid})
        await audit(u, None, "delete", name, oid)
        return {"ok": True}


admin_crud("plans", "plans")
admin_crud("modules", "modules")
admin_crud("coupons", "platform_coupons")


@r.get("/admin/settings")
async def get_settings(u=Depends(super_admin)):
    return await psettings()


@r.put("/admin/settings")
async def put_settings(body: dict = Body(...), u=Depends(super_admin)):
    await db.platform_settings.update_one({"id": "global"}, {"$set": clean(body)}, upsert=True)
    await audit(u, None, "update", "platform_settings")
    return await psettings()


async def history(cid, user, change):
    await insert("plan_history", {"id": uid(), "company_id": cid, "change": change, "user_email": user.get("email"), "created_at": now_iso()})


async def new_company(body, plan, status="trial"):
    s = await psettings()
    slug = re.sub(r"[^a-z0-9-]", "", (body.get("slug") or body["company_name"]).lower().replace(" ", "-"))
    if not slug:
        raise HTTPException(400, "El enlace del portal solo puede tener letras, números y guiones")
    if await one("companies", {"slug": slug}):
        sug = [x for x in (f"{slug}-salon", f"{slug}-gt", f"{slug}-2") if not await one("companies", {"slug": x})]
        raise HTTPException(400, f"El enlace «{slug}» ya está en uso. Pruebe: {', '.join(sug)}")
    if await one("users", {"email": body["email"].lower()}):
        raise HTTPException(400, "El correo ya está registrado")
    coupon = await one("platform_coupons", {"code": (body.get("coupon_code") or "").upper()}) if body.get("coupon_code") else None
    c = {"id": uid(), "name": body["company_name"], "slug": slug, "nit": body.get("nit") or "CF",
         "contact_name": body.get("contact_name", ""), "contact_email": body["email"].lower(), "phone": body.get("phone", ""),
         "whatsapp_number": "+" + re.sub(r"\D", "", body.get("whatsapp_number") or body.get("phone") or ""),
         "plan_id": plan["id"], "billing_cycle": body.get("billing_cycle", "monthly"), "currency": body.get("currency") or s.get("currency", "GTQ"),
         "enabled_modules": sorted(set(plan.get("included_modules", []) + body.get("modules", []))),
         "status": status, "trial_ends": (datetime.strptime(today(), "%Y-%m-%d") + timedelta(days=int(s.get("trial_days", 14)))).strftime("%Y-%m-%d"),
         "next_billing_date": None, "card": body.get("card"), "coupon_code": coupon["code"] if coupon else "",
         "coupon_pct": float(coupon["percent"]) if coupon else 0, "terms_accepted_at": now_iso(), "settings": DEFAULT_SETTINGS,
         "wa_packs": 0, "created_at": now_iso()}
    await insert("companies", c)
    hours = {str(d): ["09:00", "19:00"] for d in range(6)}
    await insert("branches", {"id": uid(), "company_id": c["id"], "name": "Sucursal Principal", "address": body.get("address", ""), "phone": c["phone"],
                              "hours": hours, "capacity": 4, "created_at": now_iso()})
    user = {"id": uid(), "email": c["contact_email"], "name": body.get("contact_name") or body["company_name"],
            "role": "company_admin", "company_id": c["id"], "password_hash": hash_pw(body["password"]), "created_at": now_iso()}
    await insert("users", user)
    return c, user


@r.get("/public/plans")
async def public_plans():
    s = await psettings()
    return {"plans": await find("plans", {"active": {"$ne": False}}, [("price_monthly", 1)]), "modules": await find("modules", {}),
            "settings": {k: s.get(k) for k in ("currency", "annual_discount", "trial_days", "tax_rate")}}


@r.post("/gateway/tokenize")
async def tokenize(body: dict = Body(...)):
    num = re.sub(r"\D", "", body.get("number") or "")
    if len(num) < 13:
        raise HTTPException(400, "Número de tarjeta inválido")
    brand = "Visa" if num[0] == "4" else "Mastercard" if num[0] == "5" else "Tarjeta"
    return {"token": f"tok_sim_{uid()}", "last4": num[-4:], "brand": brand, "exp": body.get("exp", "")}


@r.post("/signup")
async def signup(response: Response, body: dict = Body(...)):
    for f in ("company_name", "email", "password", "whatsapp_number"):
        if not body.get(f):
            raise HTTPException(400, f"Campo requerido: {f}")
    if len(body["password"]) < 8:
        raise HTTPException(400, "La contraseña debe tener al menos 8 caracteres")
    plans = await find("plans", {"active": {"$ne": False}}, [("price_monthly", 1)])
    plan = await one("plans", {"id": body.get("plan_id")}) or (plans[1] if len(plans) > 1 else plans[0])
    body["accept_terms"] = True
    if not plan:
        raise HTTPException(400, "Plan inválido")
    c, user = await new_company(body, plan)
    await history(c["id"], user, f"Alta autoservicio plan {plan['name']} ({c['billing_cycle']})")
    if int((await psettings()).get("trial_days", 14)) == 0:
        await charge(c, await create_invoice(c, await cycle_items(c)))
    user.pop("password_hash")
    token = make_token(user)
    response.set_cookie("access_token", token, httponly=True, secure=True, samesite="none", max_age=43200, path="/")
    return {"token": token, "user": user}


@r.get("/admin/companies")
async def list_companies(u=Depends(super_admin)):
    out = []
    for c in await find("companies", {}, [("created_at", -1)]):
        st = await statement(c)
        c.pop("settings", None)
        out.append({**c, "plan_name": st["plan"].get("name", ""), "mrr": await monthly_value(c), "balance": st["balance"]})
    return out


@r.post("/admin/companies")
async def create_company(body: dict = Body(...), u=Depends(super_admin)):
    plan = await one("plans", {"id": body.get("plan_id")})
    if not plan:
        raise HTTPException(400, "Plan inválido")
    c, user = await new_company(body, plan, body.get("status", "trial"))
    await history(c["id"], u, f"Alta manual plan {plan['name']}")
    return c


@r.put("/admin/companies/{cid}")
async def update_company(cid: str, body: dict = Body(...), u=Depends(super_admin)):
    allowed = {k: v for k, v in body.items() if k in ("plan_id", "billing_cycle", "coupon_pct", "coupon_code", "wa_packs",
                                                       "next_billing_date", "trial_ends", "name", "nit", "currency", "whatsapp_number")}
    await db.companies.update_one({"id": cid}, {"$set": allowed})
    await history(cid, u, "Cambio: " + ", ".join(f"{k}={v}" for k, v in allowed.items()))
    await audit(u, cid, "update", "company", allowed)
    return await one("companies", {"id": cid})


async def set_company_status(cid, status, u, reason=""):
    c = await one("companies", {"id": cid})
    if not c:
        raise HTTPException(404, "Empresa no encontrada")
    if status not in STATUS_LABEL:
        raise HTTPException(400, "Estado inválido")
    td = datetime.strptime(today(), "%Y-%m-%d")
    upd, unset = {"status": status, "status_reason": reason, "status_changed_at": now_iso()}, {}
    if status == "trial":
        upd["trial_ends"] = (td + timedelta(days=30)).strftime("%Y-%m-%d")
        unset["trial_notice_sent"] = ""
    if status == "paused":
        upd["paused_at"] = now_iso()
    if status == "cancelled":
        upd["cancelled_at"] = now_iso()
        upd["purge_after"] = (td + timedelta(days=60)).strftime("%Y-%m-%d")
    else:
        unset["purge_after"] = ""
    if status in ("active", "trial"):
        unset.update({"past_due_since": ""})
    await db.companies.update_one({"id": cid}, {"$set": upd, **({"$unset": unset} if unset else {})})
    note = f"Estado: {STATUS_LABEL.get(c['status'], c['status'])} → {STATUS_LABEL[status]}" + (f" ({reason})" if reason else "")
    await history(cid, u, note)
    await audit(u, cid, "status", "company", note)
    return await one("companies", {"id": cid})


@r.post("/admin/companies/{cid}/status")
async def change_status(cid: str, body: dict = Body(...), u=Depends(super_admin)):
    return await set_company_status(cid, body.get("status"), u, (body.get("reason") or "").strip())


async def purge_company(cid):
    for name in await db.list_collection_names():
        if name not in ("companies", "deleted_companies"):
            await db[name].delete_many({"$or": [{"company_id": cid}, {"cid": cid}]})
    await db.companies.delete_one({"id": cid})


@r.delete("/admin/companies/{cid}")
async def delete_company(cid: str, body: dict = Body(default={}), u=Depends(super_admin)):
    c = await one("companies", {"id": cid})
    if not c:
        raise HTTPException(404, "Empresa no encontrada")
    if (body.get("confirm") or "").strip() != "ELIMINAR":
        raise HTTPException(400, "Escriba la palabra de seguridad ELIMINAR para confirmar")
    await purge_company(cid)
    await db.deleted_companies.insert_one({"id": uid(), "company_id": cid, "name": c["name"], "slug": c["slug"], "by": u["email"],
                                           "reason": "manual", "deleted_at": now_iso()})
    return {"ok": True}


async def purge_expired():
    for c in await find("companies", {"status": "cancelled", "purge_after": {"$lte": today()}}):
        await purge_company(c["id"])
        await db.deleted_companies.insert_one({"id": uid(), "company_id": c["id"], "name": c["name"], "slug": c["slug"], "by": "sistema",
                                               "reason": "cancelada hace 2 meses", "deleted_at": now_iso()})


@r.post("/cron/purge-cancelled")
async def cron_purge(request: Request):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    auth = request.headers.get("Authorization") or ""
    if not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:], os.environ["WEBHOOK_CRON_SECRET"]):
        raise HTTPException(401, "No autorizado")
    try:
        env = await request.json()
    except Exception:
        env = {}
    run_id = request.headers.get("X-Webhook-Id") or (env if isinstance(env, dict) else {}).get("run_id") or uid()
    if await one("cron_runs", {"run_id": run_id}):
        return {"ok": True, "duplicate": True}
    await db.cron_runs.insert_one({"run_id": run_id, "name": "purge-cancelled", "at": now_iso()})
    task = asyncio.create_task(purge_expired())
    TASKS.add(task)
    task.add_done_callback(lambda t: (TASKS.discard(t), t.exception() and logging.error(f"purge error: {t.exception()}")))
    return {"ok": True}


async def toggle_module(c, key, enabled, user):
    mods = set(c.get("enabled_modules", []))
    inv = None
    if enabled and key not in mods:
        mods.add(key)
        await db.companies.update_one({"id": c["id"]}, {"$set": {"enabled_modules": sorted(mods)}})
        inv = await prorate_module({**c, "enabled_modules": sorted(mods)}, key)
    elif not enabled:
        mods.discard(key)
        await db.companies.update_one({"id": c["id"]}, {"$set": {"enabled_modules": sorted(mods)}})
    await history(c["id"], user, f"Módulo {key} {'habilitado' if enabled else 'deshabilitado'}")
    await audit(user, c["id"], "module", key, enabled)
    return {"enabled_modules": sorted(mods), "invoice": inv}


@r.post("/admin/companies/{cid}/modules")
async def admin_module(cid: str, body: dict = Body(...), u=Depends(super_admin)):
    c = await one("companies", {"id": cid})
    return await toggle_module(c, body["key"], bool(body.get("enabled")), u)


@r.get("/admin/companies/{cid}/statement")
async def admin_statement(cid: str, u=Depends(super_admin)):
    c = await one("companies", {"id": cid})
    return {**await statement(c), "history": await find("plan_history", {"company_id": cid}, [("created_at", -1)])}


@r.get("/admin/companies/{cid}/advance-charge")
async def advance_charge_preview(cid: str, u=Depends(super_admin)):
    c = await one("companies", {"id": cid})
    if not c:
        raise HTTPException(404, "Empresa no encontrada")
    return await advance_preview(c)


@r.post("/admin/companies/{cid}/advance-charge")
async def advance_charge_run(cid: str, body: dict = Body(default={}), u=Depends(super_admin)):
    c = await one("companies", {"id": cid})
    if not c:
        raise HTTPException(404, "Empresa no encontrada")
    if body.get("confirm") is not True:
        raise HTTPException(400, "Confirme el cobro adelantado")
    if c["status"] not in ("active", "trial"):
        raise HTTPException(400, "Solo se puede cobrar por adelantado a empresas activas o en prueba")
    if not c.get("card"):
        raise HTTPException(400, "La empresa no tiene tarjeta registrada; registre un pago manual en su lugar")
    lock = await db.companies.find_one_and_update({"id": cid, "advance_lock": {"$in": [None, False]}}, {"$set": {"advance_lock": True}})
    if not lock:
        raise HTTPException(409, "Ya hay un cobro adelantado en proceso para esta empresa")
    try:
        if await one("invoices", {"company_id": cid, "status": {"$in": ["pending", "failed"]}}):
            raise HTTPException(400, "La empresa tiene facturas pendientes; cóbrelas primero")
        ok, inv, pv = await advance_charge(await one("companies", {"id": cid}))
    finally:
        await db.companies.update_one({"id": cid}, {"$set": {"advance_lock": False}})
    await history(cid, u, f"Cobro adelantado {inv['currency']} {inv['total']:,.2f} periodo {pv['period_from']} a {pv['period_to']}: {'aprobado' if ok else 'rechazado'}")
    await audit(u, cid, "advance_charge", "invoice", f"{inv['number']} {ok}")
    if not ok:
        raise HTTPException(402, "La tarjeta fue rechazada. No se realizó el cobro y el estado de la empresa no cambió.")
    return {"ok": True, "invoice": inv["number"], "total": inv["total"], "next_billing_date": pv["period_to"]}


@r.get("/admin/payments")
async def admin_payments(u=Depends(super_admin)):
    return await find("payments", {}, [("created_at", -1)], 500)


@r.post("/admin/payments/manual")
async def manual_payment(body: dict = Body(...), u=Depends(super_admin)):
    c = await one("companies", {"id": body.get("company_id")})
    if not c:
        raise HTTPException(400, "Seleccione la empresa")
    try:
        amount = round(float(body.get("amount")), 2)
    except (TypeError, ValueError):
        raise HTTPException(400, "Escriba un monto válido")
    if amount <= 0:
        raise HTTPException(400, "El monto debe ser mayor a 0")
    method = body.get("method") or "transfer"
    if method not in METHODS:
        raise HTTPException(400, "Método de pago inválido")
    date = body.get("date") or today()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date) or date > today():
        raise HTTPException(400, "La fecha no puede ser futura")
    inv = None
    if body.get("invoice_id"):
        inv = await one("invoices", {"id": body["invoice_id"], "company_id": c["id"]})
        if not inv or inv["status"] not in ("pending", "failed"):
            raise HTTPException(400, "La factura no está pendiente")
    p = await insert("payments", {"id": uid(), "company_id": c["id"], "company_name": c["name"], "invoice_id": inv["id"] if inv else None,
                                  "invoice_number": inv["number"] if inv else "", "amount": amount, "currency": c.get("currency", "GTQ"),
                                  "method": method, "status": "approved", "reference": (body.get("reference") or "").strip(),
                                  "note": (body.get("note") or "").strip(), "manual": True, "decided_by": u["email"], "date": date, "created_at": now_iso(),
                                  "prev_invoice_status": inv["status"] if inv else None, "prev_company_status": c["status"],
                                  "prev_past_due_since": c.get("past_due_since")})
    if inv:
        paid = sum(x["amount"] for x in await find("payments", {"invoice_id": inv["id"], "status": "approved"}))
        if paid + 0.005 >= inv["total"]:
            await mark_paid(c, inv)
    await history(c["id"], u, f"Pago manual {METHODS[method]} {c.get('currency', 'GTQ')} {amount:,.2f}" + (f" a {inv['number']}" if inv else " (a cuenta)"))
    await audit(u, c["id"], "manual_payment", "payment", f"{p['id']} {amount}")
    return p


@r.post("/admin/payments/{pid}/void")
async def void_payment(pid: str, body: dict = Body(default={}), u=Depends(super_admin)):
    p = await one("payments", {"id": pid})
    if not p or not p.get("manual") or p["status"] != "approved":
        raise HTTPException(400, "Solo se pueden anular pagos manuales aprobados")
    reason = (body.get("reason") or "").strip()
    if not reason:
        raise HTTPException(400, "Escriba el motivo de la anulación")
    await db.payments.update_one({"id": pid}, {"$set": {"status": "void", "void_reason": reason, "voided_by": u["email"], "voided_at": now_iso()}})
    if p.get("invoice_id"):
        inv = await one("invoices", {"id": p["invoice_id"]})
        paid = sum(x["amount"] for x in await find("payments", {"invoice_id": p["invoice_id"], "status": "approved"}))
        if inv and inv["status"] == "paid" and paid + 0.005 < inv["total"]:
            await db.invoices.update_one({"id": inv["id"]}, {"$set": {"status": p.get("prev_invoice_status") or "pending"}, "$unset": {"paid_at": ""}})
            co = await one("companies", {"id": p["company_id"]})
            prev = p.get("prev_company_status")
            if co and co["status"] == "active" and prev in ("past_due", "suspended_partial", "suspended"):
                await db.companies.update_one({"id": co["id"]}, {"$set": {"status": prev, "past_due_since": p.get("prev_past_due_since")}})
    await history(p["company_id"], u, f"Pago anulado {p.get('currency', 'GTQ')} {p['amount']:,.2f}: {reason}")
    await audit(u, p["company_id"], "void_payment", "payment", f"{pid} {reason}")
    return {"ok": True}


async def statement_response(c, start, end, format):
    end = end or today()
    start = start or end[:8] + "01"
    if start > end:
        raise HTTPException(400, "La fecha inicial debe ser anterior a la final")
    st = await account_statement(c, start, end)
    name = f"estado_cuenta_{c['slug']}_{start}_{end}"
    if format == "pdf":
        return Response(account_statement_pdf(st), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={name}.pdf"})
    if format == "xlsx":
        from routes_extra import xlsx
        rows = [[st["start"], "", "Saldo anterior", "", "", st["opening"]]] + [[r["date"], r["doc"], r["desc"], r["charge"] or "", r["payment"] or "", r["balance"]] for r in st["rows"]]
        rows.append(["", "", "Saldo al cierre", st["charges"], st["payments"], st["closing"]])
        return xlsx(["Fecha", "Documento", "Concepto", "Cargo", "Abono", "Saldo"], rows, name)
    return st


@r.get("/admin/companies/{cid}/account-statement")
async def admin_account_statement(cid: str, start: str = "", end: str = "", format: str = "json", u=Depends(super_admin)):
    c = await one("companies", {"id": cid})
    if not c:
        raise HTTPException(404, "Empresa no encontrada")
    return await statement_response(c, start, end, format)


@r.get("/billing/account-statement")
async def my_account_statement(start: str = "", end: str = "", format: str = "json", c=Depends(guard(("company_admin",)))):
    return await statement_response(c["company"], start, end, format)


@r.post("/admin/payments/{pid}/decision")
async def payment_decision(pid: str, body: dict = Body(...), u=Depends(super_admin)):
    p = await one("payments", {"id": pid})
    if not p or p["status"] != "pending":
        raise HTTPException(400, "Pago no pendiente")
    ok = bool(body.get("approve"))
    await db.payments.update_one({"id": pid}, {"$set": {"status": "approved" if ok else "rejected", "decided_by": u["email"]}})
    if ok and p.get("invoice_id"):
        c = await one("companies", {"id": p["company_id"]})
        inv = await one("invoices", {"id": p["invoice_id"]})
        if inv:
            await mark_paid(c, inv)
    await audit(u, p["company_id"], "payment_decision", "payment", f"{pid} {ok}")
    return {"ok": True}


@r.get("/admin/metrics")
async def metrics(u=Depends(super_admin)):
    s = await psettings()
    companies = await find("companies", {})
    counts = {k: 0 for k in ("trial", "active", "past_due", "suspended_partial", "suspended", "cancelled")}
    mrr, wa = 0.0, []
    month = today()[:8] + "01"
    for c in companies:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
        if c["status"] in ("active", "past_due"):
            mrr += await monthly_value(c)
        msgs = await db.wa_messages.count_documents({"company_id": c["id"], "created_at": {"$gte": month}})
        billed = sum(i["amount"] for i in await breakdown(c) if "WhatsApp" in i["desc"])
        wa.append({"company": c["name"], "messages": msgs, "cost": round(msgs * float(s.get("wa_cost_per_message", 0.05)), 2), "billed": billed})
    invoices = await find("invoices", {"status": "paid"})
    by_plan, by_module, by_month = {}, {}, {}
    for i in invoices:
        for it in i["items"]:
            if it.get("kind") == "plan":
                by_plan[i.get("plan_name") or "-"] = by_plan.get(i.get("plan_name") or "-", 0) + it["amount"]
            if it.get("kind") == "module":
                by_module[it["desc"]] = by_module.get(it["desc"], 0) + it["amount"]
        by_month[i["date"][:7]] = by_month.get(i["date"][:7], 0) + i["total"]
    trials = [c for c in companies if c.get("trial_ends")]
    converted = [c for c in trials if c.get("converted")]
    since = (datetime.strptime(today(), "%Y-%m-%d") - timedelta(days=30)).isoformat()
    cancelled_recent = sum(1 for c in companies if c["status"] == "cancelled" and (c.get("cancelled_at") or "") >= since)
    base = counts["active"] + counts["past_due"] + cancelled_recent
    return {"mrr": round(mrr, 2), "arr": round(mrr * 12, 2), "counts": counts, "total": len(companies),
            "churn": round(cancelled_recent / base * 100, 1) if base else 0,
            "trial_conversion": round(len(converted) / len(trials) * 100, 1) if trials else 0,
            "by_plan": [{"name": k, "value": round(v, 2)} for k, v in by_plan.items()],
            "by_module": [{"name": k, "value": round(v, 2)} for k, v in by_module.items()],
            "by_month": [{"month": k, "value": round(v, 2)} for k, v in sorted(by_month.items())],
            "whatsapp": wa, "currency": s.get("currency", "GTQ")}


@r.get("/admin/export")
async def export_xlsx(u=Depends(super_admin)):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Estado de cuenta"
    ws.append(["Empresa", "NIT", "Estado", "Plan", "Ciclo", "Cargos", "Pagos", "Saldo", "Próximo cobro", "MRR"])
    for c in await find("companies", {}):
        st = await statement(c)
        ws.append([c["name"], c.get("nit"), c["status"], st["plan"].get("name"), c.get("billing_cycle"), st["charged"], st["paid"],
                   st["balance"], c.get("next_billing_date") or c.get("trial_ends"), await monthly_value(c)])
    ws2 = wb.create_sheet("Facturas")
    ws2.append(["Número", "Empresa", "Fecha", "Total", "Moneda", "Estado"])
    for i in await find("invoices", {}, [("created_at", -1)]):
        ws2.append([i["number"], i["company_name"], i["date"], i["total"], i["currency"], i["status"]])
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=estado_cuenta_consolidado.xlsx"})


@r.get("/invoices/{iid}/pdf")
async def get_pdf(iid: str, user=Depends(get_user)):
    inv = await one("invoices", {"id": iid})
    if not inv or (user["role"] != "super_admin" and inv["company_id"] != user.get("company_id")):
        raise HTTPException(404, "Factura no encontrada")
    return Response(invoice_pdf(inv), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={inv['number']}.pdf"})


@r.get("/public/slug-check")
async def slug_check(slug: str):
    s = re.sub(r"[^a-z0-9-]", "", slug.lower().replace(" ", "-"))
    if not s:
        return {"slug": s, "available": False, "suggestions": []}
    if not await one("companies", {"slug": s}):
        return {"slug": s, "available": True, "suggestions": []}
    sug = [x for x in (f"{s}-salon", f"{s}-gt", f"{s}-2", f"salon-{s}") if not await one("companies", {"slug": x})]
    return {"slug": s, "available": False, "suggestions": sug[:3]}


@r.post("/billing/activate")
async def activate(body: dict = Body(...), c=Depends(guard(("company_admin",)))):
    plan = await one("plans", {"id": body.get("plan_id")})
    if not plan or not body.get("nit") or not body.get("card"):
        raise HTTPException(400, "Seleccione plan e ingrese NIT y tarjeta")
    mods = sorted(set(c["company"].get("enabled_modules", [])) | set(plan.get("included_modules", [])))
    await db.companies.update_one({"id": c["cid"]}, {"$set": {"plan_id": plan["id"], "nit": body["nit"], "card": body["card"], "enabled_modules": mods,
                                                              "billing_cycle": body.get("billing_cycle", "monthly")}})
    co = await one("companies", {"id": c["cid"]})
    inv = await create_invoice(co, await cycle_items(co))
    ok = await charge(co, inv)
    await history(c["cid"], c["user"], f"Activación plan {plan['name']} ({'aprobado' if ok else 'rechazado'})")
    if not ok:
        raise HTTPException(402, "La tarjeta fue rechazada. Intente con otra tarjeta")
    return {"ok": True, "invoice": inv}


@r.post("/billing/quote")
async def quote(body: dict = Body(...), c=Depends(guard(("company_admin",)))):
    co = {**c["company"], "plan_id": body.get("plan_id"), "billing_cycle": body.get("billing_cycle", "monthly")}
    plan = await one("plans", {"id": body.get("plan_id")}) or {}
    co["enabled_modules"] = sorted(set(co.get("enabled_modules", [])) | set(plan.get("included_modules", [])))
    items = await cycle_items(co)
    s = await psettings()
    sub = round(sum(i["amount"] for i in items), 2)
    tax = round(sub * float(s.get("tax_rate", 12)) / 100, 2)
    return {"items": items, "subtotal": sub, "tax": tax, "total": round(sub + tax, 2), "tax_rate": s.get("tax_rate", 12)}


@r.get("/billing/statement")
async def my_statement(c=Depends(ctx)):
    return {**await statement(c["company"]), "history": await find("plan_history", {"company_id": c["cid"]}, [("created_at", -1)]),
            "notifications": await find("notifications", {"company_id": c["cid"]}, [("created_at", -1)], 20)}


@r.post("/billing/card")
async def update_card(body: dict = Body(...), c=Depends(guard(("company_admin",)))):
    card = {"token": body["token"], "last4": body["last4"], "brand": body.get("brand", ""), "exp": body.get("exp", "")}
    await db.companies.update_one({"id": c["cid"]}, {"$set": {"card": card}})
    await audit(c["user"], c["cid"], "update", "card", card["last4"])
    return card


@r.post("/billing/modules")
async def contract_module(body: dict = Body(...), c=Depends(guard(("company_admin",)))):
    return await toggle_module(c["company"], body["key"], bool(body.get("enabled", True)), c["user"])


@r.put("/billing/plan")
async def change_plan(body: dict = Body(...), c=Depends(guard(("company_admin",)))):
    plan = await one("plans", {"id": body.get("plan_id")})
    if not plan:
        raise HTTPException(400, "Plan inválido")
    mods = sorted(set(c["company"].get("enabled_modules", [])) | set(plan.get("included_modules", [])))
    await db.companies.update_one({"id": c["cid"]}, {"$set": {"plan_id": plan["id"], "enabled_modules": mods,
                                                              "billing_cycle": body.get("billing_cycle", c["company"].get("billing_cycle"))}})
    await history(c["cid"], c["user"], f"Cambio a plan {plan['name']} ({body.get('billing_cycle')})")
    return {"ok": True}


@r.post("/billing/pay/{iid}")
async def pay_invoice(iid: str, c=Depends(guard(("company_admin",)))):
    inv = await one("invoices", {"id": iid, "company_id": c["cid"]})
    if not inv or inv["status"] == "paid":
        raise HTTPException(400, "Factura no disponible para pago")
    return {"ok": await charge(c["company"], inv)}


@r.post("/billing/transfer")
async def register_transfer(body: dict = Body(...), c=Depends(guard(("company_admin",)))):
    inv = await one("invoices", {"id": body.get("invoice_id"), "company_id": c["cid"]})
    if not inv:
        raise HTTPException(400, "Factura inválida")
    return await insert("payments", {"id": uid(), "company_id": c["cid"], "company_name": c["company"]["name"], "invoice_id": inv["id"],
                                     "invoice_number": inv["number"], "amount": inv["total"], "currency": inv["currency"],
                                     "method": "transfer", "status": "pending", "reference": body.get("reference", ""),
                                     "date": today(), "created_at": now_iso()})


@r.post("/billing/cancel")
async def cancel_service(c=Depends(guard(("company_admin",)))):
    await db.companies.update_one({"id": c["cid"]}, {"$set": {"status": "cancelled", "cancelled_at": now_iso(),
                                                         "purge_after": (datetime.strptime(today(), "%Y-%m-%d") + timedelta(days=60)).strftime("%Y-%m-%d")}})
    await history(c["cid"], c["user"], "Cancelación del servicio")
    return {"ok": True}


@r.get("/billing/export")
async def export_data(c=Depends(guard(("company_admin",)))):
    data = {coll: await find(coll, {"company_id": c["cid"]}) for coll in
            ("branches", "stylists", "services", "clients", "appointments", "waitlist", "invoices", "payments")}
    return data
