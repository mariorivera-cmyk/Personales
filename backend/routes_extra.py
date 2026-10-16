import io
import base64
from fastapi import APIRouter, Depends, Body, HTTPException, UploadFile, File, Response
from core import (db, find, one, uid, now_iso, today, insert, audit, guard, wa_send, norm_phone, portal_url, notify_company,
                  MANAGERS, STAFF, ALL_STAFF)
import engine as E
import rules as R
from routes_ops import crud

r = APIRouter(prefix="/api")
METHODS = ("cash", "card", "transfer")
TEMPLATES = [("Corte de dama", "Cabello", 45, 150), ("Corte de caballero", "Cabello", 30, 80), ("Tinte completo", "Color", 120, 450),
             ("Retoque de raíz", "Color", 90, 300), ("Mechas / Balayage", "Color", 180, 1100), ("Peinado", "Peinado", 45, 175),
             ("Manicure", "Uñas", 40, 100), ("Pedicure", "Uñas", 50, 150), ("Uñas acrílicas", "Uñas", 90, 250),
             ("Keratina", "Tratamientos", 150, 900), ("Tratamiento hidratante", "Tratamientos", 45, 200),
             ("Arreglo de barba", "Barbería", 30, 70), ("Depilación de cejas", "Estética", 20, 60), ("Maquillaje social", "Maquillaje", 60, 300)]

crud("products", "products", write=MANAGERS)
crud("gallery", "gallery", write=MANAGERS)


def xlsx(headers, rows, name):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename={name}.xlsx"})


def check_payments(pays, total):
    pays = [{"method": p.get("method"), "amount": round(float(p.get("amount") or 0), 2)} for p in pays if float(p.get("amount") or 0) > 0]
    if any(p["method"] not in METHODS for p in pays):
        raise HTTPException(400, "Método de pago inválido")
    paid = round(sum(p["amount"] for p in pays), 2)
    if abs(paid - total) > 0.01:
        raise HTTPException(400, f"La suma de los pagos (Q{paid:.2f}) debe ser igual al total (Q{total:.2f})")
    return pays


@r.get("/clients/lookup")
async def client_lookup(phone: str, branch_id: str = "", c=Depends(guard(ALL_STAFF))):
    cl = await one("clients", {"company_id": c["cid"], "phone": norm_phone(phone)})
    if not cl:
        return {"exists": False}
    from core import dec
    ru = R.effective(c["company"], branch_id or None)
    faults = await R.fault_count(cl["id"], ru)
    mx = int(ru["noshow_limit"])
    return {"exists": True, "client": {"id": cl["id"], "name": cl["name"], "email": cl.get("email")}, "no_shows": faults,
            "allergies": dec((cl.get("notes") or {}).get("allergies", "")), "alert": ru["noshow_enabled"] and faults >= mx, "max_no_shows": mx,
            "noshow_action": R.DEFS["noshow_action"]["options"][ru["noshow_action"]], "deposit_next": bool(cl.get("deposit_next"))}


@r.post("/appointments/{oid}/checkout")
async def checkout(oid: str, body: dict = Body(...), c=Depends(guard(ALL_STAFF))):
    a = await one("appointments", {"id": oid, "company_id": c["cid"]})
    if not a or a["status"] in ("completed", "cancelled"):
        raise HTTPException(400, "La cita no puede cerrarse en su estado actual")
    discount, tip = round(float(body.get("discount") or 0), 2), round(float(body.get("tip") or 0), 2)
    if discount and not (body.get("discount_reason") or "").strip():
        raise HTTPException(400, "Indique el motivo del descuento")
    if discount < 0 or tip < 0 or discount > a["price"]:
        raise HTTPException(400, "Descuento o propina inválidos")
    dep = float(a.get("deposit_paid") or 0)
    total = round(a["price"] - discount - dep + tip, 2)
    pays = check_payments(body.get("payments") or [], total)
    st = await one("stylists", {"id": a["stylist_id"]}) or {}
    svc = await one("services", {"id": a["service_id"]}) or {}
    ru = R.effective(c["company"], a["branch_id"])
    set_ = lambda d, k: d.get(k) not in (None, "")
    pct = float(svc["commission_pct"]) if set_(svc, "commission_pct") else float(st["commission_pct"]) if set_(st, "commission_pct") else float(ru["commission_percent"])
    fixed = float(st["commission_fixed"]) if set_(st, "commission_fixed") and float(st["commission_fixed"]) else float(ru["commission_fixed"])
    net = round(a["price"] - discount, 2)
    tips_in = ru["tips_in_commission"] or bool(st.get("tips_in_commission"))
    base = fixed if ru["commission_model"] == "fixed" else net * pct / 100
    comm = round(base + (tip * pct / 100 if tips_in and ru["commission_model"] != "fixed" else 0), 2)
    try:
        await E.set_status(c["cid"], oid, "completed", c["user"])
    except E.BookingError as e:
        raise HTTPException(400, e.msg)
    sale = {"id": uid(), "company_id": c["cid"], "kind": "service", "appointment_id": oid, "branch_id": a["branch_id"], "branch_name": a["branch_name"],
            "stylist_id": a["stylist_id"], "stylist_name": a["stylist_name"], "client_name": a["client_name"],
            "description": ", ".join([a["service_name"]] + a.get("addon_names", [])), "date": today(), "subtotal": a["price"],
            "discount": discount, "discount_reason": body.get("discount_reason", ""), "tip": tip, "deposit_applied": dep, "net": net,
            "payments": pays, "total": total, "commission": comm, "created_by": c["user"]["email"], "voided": False, "created_at": now_iso()}
    await insert("sales", sale)
    await db.appointments.update_one({"id": oid}, {"$set": {"paid_net": net, "tip": tip, "commission": comm, "sale_id": sale["id"], "paid_date": today()}})
    await audit(c["user"], c["cid"], "checkout", "appointment", f"{oid} total {total}" + (f" descuento {discount}: {body.get('discount_reason')}" if discount else ""))
    return sale


@r.post("/appointments/{oid}/deposit")
async def deposit_received(oid: str, body: dict = Body(default={}), c=Depends(guard(STAFF))):
    a = await one("appointments", {"id": oid, "company_id": c["cid"]})
    if not a or not a.get("deposit_required"):
        raise HTTPException(400, "La cita no requiere anticipo")
    amt = float(body.get("amount") or a["deposit_required"])
    await db.appointments.update_one({"id": oid}, {"$set": {"deposit_status": "received", "deposit_paid": amt, "deposit_ref": body.get("reference", ""),
                                                            "status": "confirmed" if a["status"] == "pending" else a["status"]}})
    await wa_send(c["cid"], a["client_phone"], f"Recibimos su anticipo de Q{amt:.2f}. Su cita del {a['date']} a las {a['time']} está confirmada.", "confirmation")
    await audit(c["user"], c["cid"], "deposit", "appointment", f"{oid} {amt}")
    return {"ok": True}


@r.post("/sales/{sid}/void")
async def void_sale(sid: str, body: dict = Body(default={}), c=Depends(guard(("company_admin",)))):
    s = await one("sales", {"id": sid, "company_id": c["cid"]})
    if not s or s["voided"]:
        raise HTTPException(400, "Cobro no válido")
    await db.sales.update_one({"id": sid}, {"$set": {"voided": True, "void_reason": body.get("reason", ""), "voided_by": c["user"]["email"]}})
    if s.get("appointment_id"):
        a = await one("appointments", {"id": s["appointment_id"]}) or {}
        if a and "loyalty" in c["company"].get("enabled_modules", []):
            per = float(R.effective(c["company"], a.get("branch_id"))["loyalty_points_per_100"])
            await db.clients.update_one({"id": a["client_id"]}, {"$inc": {"points": -int(a["price"] / 100 * per)}})
        for sv in await find("services", {"id": {"$in": [a.get("service_id")] + a.get("addon_ids", [])}}):
            for item in sv.get("consumes") or []:
                await E.stock_move(c["cid"], item["product_id"], float(item.get("qty") or 1), "Anulación de cobro", sid)
        await db.appointments.update_one({"id": s["appointment_id"]}, {"$set": {"status": "confirmed"}, "$unset": {"paid_net": "", "sale_id": "", "commission": ""}})
    for it in s.get("items", []):
        await E.stock_move(c["cid"], it["product_id"], it["qty"], "Anulación de venta", sid)
    await audit(c["user"], c["cid"], "void", "sale", f"{sid} {body.get('reason', '')}")
    return {"ok": True}


@r.get("/cash")
async def cash_close(date: str = "", branch_id: str = "", format: str = "", c=Depends(guard(STAFF))):
    q = {"company_id": c["cid"], "date": date or today()}
    if branch_id:
        q["branch_id"] = branch_id
    sales = await find("sales", q, [("created_at", 1)])
    from datetime import datetime
    from core import TZ
    for s in sales:
        s["local_time"] = datetime.fromisoformat(s["created_at"]).astimezone(TZ).strftime("%H:%M")
    ok = [s for s in sales if not s["voided"]]
    by_method, by_branch, by_stylist = {}, {}, {}
    for s in ok:
        for p in s["payments"]:
            by_method[p["method"]] = round(by_method.get(p["method"], 0) + p["amount"], 2)
        by_branch[s.get("branch_name") or "-"] = round(by_branch.get(s.get("branch_name") or "-", 0) + s["total"], 2)
        k = s.get("stylist_name") or "Mostrador"
        x = by_stylist.setdefault(k, {"name": k, "sales": 0, "tips": 0})
        x["sales"] = round(x["sales"] + s["net"], 2)
        x["tips"] = round(x["tips"] + s["tip"], 2)
    res = {"date": q["date"], "sales": sales, "by_method": by_method, "by_branch": by_branch, "by_stylist": list(by_stylist.values()),
           "total": round(sum(s["total"] for s in ok), 2), "tips": round(sum(s["tip"] for s in ok), 2),
           "discounts": round(sum(s["discount"] for s in ok), 2), "count": len(ok)}
    if format == "xlsx":
        rows = [[s["local_time"], s["description"], s.get("stylist_name") or "Mostrador", s.get("branch_name"), s["net"], s["tip"],
                 ", ".join(f"{p['method']} {p['amount']}" for p in s["payments"]), s["total"], "ANULADO" if s["voided"] else ""] for s in sales]
        rows += [[], ["Por método"]] + [[k, v] for k, v in by_method.items()]
        return xlsx(["Hora", "Concepto", "Estilista", "Sucursal", "Neto", "Propina", "Pagos", "Total", "Estado"], rows, f"cierre_{q['date']}")
    return res


@r.get("/commissions")
async def commissions(start: str, end: str, format: str = "", c=Depends(guard(MANAGERS))):
    stylists = {s["id"]: s for s in await find("stylists", {"company_id": c["cid"]})}
    rows = {}
    rng = {"$gte": start, "$lte": end}
    for a in await find("appointments", {"company_id": c["cid"], "status": "completed",
                                         "$or": [{"paid_date": rng}, {"paid_date": {"$exists": False}, "date": rng}]}):
        st = stylists.get(a["stylist_id"], {})
        x = rows.setdefault(a["stylist_id"], {"stylist": a["stylist_name"], "services": 0, "sales": 0, "tips": 0, "commission": 0,
                                              "base_salary": float(st.get("base_salary") or 0)})
        x["services"] += 1
        x["sales"] = round(x["sales"] + a.get("paid_net", a["price"]), 2)
        x["tips"] = round(x["tips"] + float(a.get("tip") or 0), 2)
        x["commission"] = round(x["commission"] + float(a.get("commission") or 0), 2)
    out = [{**x, "total_pay": round(x["base_salary"] + x["commission"] + x["tips"], 2)} for x in rows.values()]
    if format == "xlsx":
        return xlsx(["Estilista", "Servicios", "Ventas", "Propinas", "Comisión", "Sueldo base", "Total a pagar"],
                    [[x["stylist"], x["services"], x["sales"], x["tips"], x["commission"], x["base_salary"], x["total_pay"]] for x in out], f"comisiones_{start}_{end}")
    return out


@r.get("/service-templates")
async def service_templates(c=Depends(guard(("company_admin",)))):
    f = 1 / 7.8 if c["company"].get("currency") == "USD" else 1
    return [{"name": n, "category": cat, "duration": d, "price": round(p * f, 2)} for n, cat, d, p in TEMPLATES]


async def ensure_category(cid, name):
    name = (name or "").strip()
    if name and not await one("service_categories", {"company_id": cid, "name": name}):
        await insert("service_categories", {"id": uid(), "company_id": cid, "name": name, "created_at": now_iso()})


@r.get("/service-categories")
async def list_categories(c=Depends(guard(None))):
    for s in await find("services", {"company_id": c["cid"]}):
        await ensure_category(c["cid"], s.get("category"))
    cats = await find("service_categories", {"company_id": c["cid"]}, [("name", 1)])
    for x in cats:
        x["services"] = await db.services.count_documents({"company_id": c["cid"], "category": x["name"]})
    return cats


@r.post("/service-categories")
async def create_category(body: dict = Body(...), c=Depends(guard(("company_admin",)))):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Escriba el nombre de la categoría")
    if await one("service_categories", {"company_id": c["cid"], "name": {"$regex": f"^{__import__('re').escape(name)}$", "$options": "i"}}):
        raise HTTPException(400, "Esa categoría ya existe")
    await ensure_category(c["cid"], name)
    await audit(c["user"], c["cid"], "create", "service-categories", name)
    return await one("service_categories", {"company_id": c["cid"], "name": name})


@r.put("/service-categories/{oid}")
async def rename_category(oid: str, body: dict = Body(...), c=Depends(guard(("company_admin",)))):
    cat = await one("service_categories", {"id": oid, "company_id": c["cid"]})
    name = (body.get("name") or "").strip()
    if not cat or not name:
        raise HTTPException(400, "Escriba el nombre de la categoría")
    if name != cat["name"] and await one("service_categories", {"company_id": c["cid"], "name": name}):
        raise HTTPException(400, "Esa categoría ya existe")
    await db.service_categories.update_one({"id": oid}, {"$set": {"name": name}})
    await db.services.update_many({"company_id": c["cid"], "category": cat["name"]}, {"$set": {"category": name}})
    await audit(c["user"], c["cid"], "update", "service-categories", f"{cat['name']} → {name}")
    return {"ok": True}


@r.delete("/service-categories/{oid}")
async def delete_category(oid: str, c=Depends(guard(("company_admin",)))):
    cat = await one("service_categories", {"id": oid, "company_id": c["cid"]})
    if not cat:
        raise HTTPException(404, "Categoría no encontrada")
    n = await db.services.count_documents({"company_id": c["cid"], "category": cat["name"]})
    if n:
        raise HTTPException(400, f"No se puede eliminar: {n} servicio(s) usan esta categoría. Cámbielos primero.")
    await db.service_categories.delete_one({"id": oid})
    await audit(c["user"], c["cid"], "delete", "service-categories", cat["name"])
    return {"ok": True}


@r.post("/service-templates")
async def add_templates(body: dict = Body(...), c=Depends(guard(("company_admin",)))):
    items = body.get("items") or []
    for it in items:
        await ensure_category(c["cid"], it.get("category"))
        await insert("services", {"id": uid(), "company_id": c["cid"], "name": it["name"], "category": it.get("category", ""), "description": "",
                                  "duration": int(it["duration"]), "price": float(it["price"]), "prep_minutes": 0, "cleanup_minutes": 10,
                                  "deposit": 0, "stylist_ids": [], "active": True, "created_at": now_iso()})
    await audit(c["user"], c["cid"], "create", "services", f"{len(items)} desde plantilla")
    return {"created": len(items)}


@r.get("/onboarding")
async def onboarding(c=Depends(guard(STAFF))):
    co, cid = c["company"], c["cid"]
    branches = await find("branches", {"company_id": cid})
    ob = co.get("onboarding") or {}
    steps = [
        {"key": "services", "label": "Agregue sus servicios", "to": "/app/servicios", "done": await db.services.count_documents({"company_id": cid}) > 0},
        {"key": "stylists", "label": "Registre estilistas y horarios", "to": "/app/estilistas", "done": await db.stylists.count_documents({"company_id": cid}) > 0},
        {"key": "salon", "label": "Complete datos del salón (descripción y dirección)", "to": "/app/config",
         "done": bool(co.get("description")) and bool(branches) and all(b.get("address") for b in branches)},
        {"key": "rules", "label": "Revise las reglas del salón (cancelación, anticipo, faltas)", "to": "/app/config?tab=reglas", "done": bool(co.get("rules_reviewed"))},
        {"key": "share", "label": "Comparta su enlace de reservas", "to": None, "done": bool(ob.get("shared"))},
    ]
    return {"steps": steps, "dismissed": bool(ob.get("dismissed")), "portal_url": portal_url(co["slug"])}


@r.post("/onboarding")
async def onboarding_update(body: dict = Body(...), c=Depends(guard(STAFF))):
    upd = {f"onboarding.{k}": bool(v) for k, v in body.items() if k in ("shared", "dismissed")}
    await db.companies.update_one({"id": c["cid"]}, {"$set": upd})
    return {"ok": True}


@r.get("/dashboard/alerts")
async def dashboard_alerts(c=Depends(guard(STAFF))):
    cid, td = c["cid"], today()
    from core import local_now
    now = local_now().strftime("%H:%M")
    pend = [a for a in await find("appointments", {"company_id": cid, "status": {"$in": ["pending", "confirmed"]}, "date": {"$lte": td}}, [("date", -1)], 200)
            if a["date"] < td or a["end_time"] <= now]
    low = [p for p in await find("products", {"company_id": cid}) if float(p.get("stock") or 0) <= float(p.get("min_stock") or 0)]
    noaddr = [b["name"] for b in await find("branches", {"company_id": cid}) if not b.get("address")]
    return {"pending_close": pend[:30], "low_stock": low, "missing_address": noaddr,
            "notifications": await find("notifications", {"company_id": cid}, [("created_at", -1)], 8)}


@r.post("/products/{pid}/adjust")
async def adjust(pid: str, body: dict = Body(...), c=Depends(guard(MANAGERS))):
    if not (body.get("reason") or "").strip():
        raise HTTPException(400, "Indique el motivo del ajuste")
    await E.stock_move(c["cid"], pid, float(body["qty"]), "Ajuste: " + body["reason"])
    await audit(c["user"], c["cid"], "adjust", "product", f"{pid} {body['qty']} {body['reason']}")
    return {"ok": True}


@r.post("/products/sale")
async def product_sale(body: dict = Body(...), c=Depends(guard(STAFF))):
    items, total = [], 0
    for it in body.get("items") or []:
        p = await one("products", {"id": it["product_id"], "company_id": c["cid"]})
        qty = float(it.get("qty") or 0)
        if not p or qty <= 0:
            raise HTTPException(400, "Producto inválido")
        if float(p.get("stock") or 0) < qty:
            raise HTTPException(400, f"Existencia insuficiente de {p['name']}")
        items.append({"product_id": p["id"], "name": p["name"], "qty": qty, "price": float(p["price"])})
        total += qty * float(p["price"])
    if not items:
        raise HTTPException(400, "Agregue productos")
    total = round(total, 2)
    pays = check_payments(body.get("payments") or [], total)
    branch = await one("branches", {"id": body.get("branch_id")}) or {}
    sale = {"id": uid(), "company_id": c["cid"], "kind": "product", "branch_id": branch.get("id"), "branch_name": branch.get("name", ""),
            "stylist_id": None, "stylist_name": "Mostrador", "client_name": body.get("client_name", ""), "items": items,
            "description": ", ".join(f"{i['qty']:g} x {i['name']}" for i in items), "date": today(), "subtotal": total, "discount": 0, "tip": 0,
            "deposit_applied": 0, "net": total, "payments": pays, "total": total, "commission": 0, "created_by": c["user"]["email"],
            "voided": False, "created_at": now_iso()}
    await insert("sales", sale)
    for i in items:
        await E.stock_move(c["cid"], i["product_id"], -i["qty"], "Venta mostrador", sale["id"])
    return sale


@r.get("/inventory")
async def inventory(c=Depends(guard(STAFF))):
    prods = await find("products", {"company_id": c["cid"]})
    return {"products": prods, "moves": await find("inventory_moves", {"company_id": c["cid"]}, [("created_at", -1)], 200),
            "value": round(sum(float(p.get("stock") or 0) * float(p.get("cost") or 0) for p in prods), 2)}


@r.post("/company/media")
async def upload_media(file: UploadFile = File(...), c=Depends(guard(MANAGERS))):
    data = await file.read()
    if not (file.content_type or "").startswith("image/") or len(data) > 2 * 1024 * 1024:
        raise HTTPException(400, "Suba una imagen de máximo 2MB")
    mid = uid()
    await db.media.insert_one({"id": mid, "company_id": c["cid"], "content_type": file.content_type, "data": base64.b64encode(data).decode(), "created_at": now_iso()})
    return {"id": mid, "url": f"/api/media/{mid}"}


@r.get("/media/{mid}")
async def get_media(mid: str):
    m = await one("media", {"id": mid})
    if not m:
        raise HTTPException(404, "Imagen no encontrada")
    return Response(base64.b64decode(m["data"]), media_type=m["content_type"], headers={"Cache-Control": "public, max-age=86400"})


@r.get("/reviews")
async def reviews(c=Depends(guard(STAFF))):
    return await find("reviews", {"company_id": c["cid"]}, [("created_at", -1)], 300)


@r.put("/reviews/{rid}")
async def moderate(rid: str, body: dict = Body(...), c=Depends(guard(("company_admin",)))):
    await db.reviews.update_one({"id": rid, "company_id": c["cid"]}, {"$set": {"hidden": bool(body.get("hidden"))}})
    return {"ok": True}


async def notify_low_rating(cid, rev):
    if rev["rating"] <= 2:
        await notify_company(cid, "Calificación baja", f"{rev['client_name']} calificó {rev['rating']}/5: {rev.get('comment', '')}")
