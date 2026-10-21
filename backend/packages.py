import re
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Body, HTTPException
from core import db, find, one, uid, now_iso, today, insert, audit, guard, wa_send, STAFF, ALL_STAFF
from routes_ops import crud

r = APIRouter(prefix="/api")
OWNER = ("company_admin",)


def num(body, key, cast, msg):
    try:
        v = cast(float(body.get(key)))
    except (TypeError, ValueError):
        raise HTTPException(400, msg)
    if v <= 0:
        raise HTTPException(400, msg)
    body[key] = v


async def pkg_validate(c, body, partial=False):
    if partial and "items" not in body:
        if "price" in body:
            num(body, "price", float, "Indique el precio del paquete")
        if "validity_days" in body:
            num(body, "validity_days", int, "Indique la vigencia en días")
        return
    items = []
    for it in body.get("items") or []:
        s = await one("services", {"id": it.get("service_id"), "company_id": c["cid"]})
        try:
            q = int(it.get("qty") or 0)
        except (TypeError, ValueError):
            q = 0
        if not s or q <= 0:
            raise HTTPException(400, "Revise los servicios y cantidades del paquete")
        items.append({"service_id": s["id"], "service_name": s["name"], "qty": q})
    if not items:
        raise HTTPException(400, "Agregue al menos un servicio al paquete")
    num(body, "price", float, "Indique el precio del paquete")
    num(body, "validity_days", int, "Indique la vigencia en días")
    body.update(items=items)


crud("packages", "packages", validate=pkg_validate)


def remaining(cp, service_id=None):
    return sum(i["qty"] - i["used"] for i in cp["items"] if not service_id or i["service_id"] == service_id)


def state(cp):
    if cp["status"] == "voided":
        return "voided"
    if remaining(cp) == 0:
        return "exhausted"
    return "expired" if cp["expires"] < today() else "active"


def view(cp):
    return {**cp, "status": state(cp), "remaining": remaining(cp), "total": sum(i["qty"] for i in cp["items"])}


async def get_cp(c, cid_):
    cp = await one("client_packages", {"id": cid_, "company_id": c["cid"]})
    if not cp:
        raise HTTPException(404, "Paquete no encontrado")
    return cp


async def consume(cid, cp, service_id, user, appointment_id=None, note=""):
    if state(cp) != "active":
        raise HTTPException(400, "El paquete no está vigente")
    item = next((i for i in cp["items"] if i["service_id"] == service_id and i["used"] < i["qty"]), None)
    if not item:
        raise HTTPException(400, "El paquete no tiene sesiones disponibles de este servicio")
    use = {"id": uid(), "date": today(), "service_id": service_id, "service_name": item["service_name"],
           "appointment_id": appointment_id, "by": user.get("email", ""), "note": note, "created_at": now_iso()}
    res = await db.client_packages.update_one({"id": cp["id"], "items": {"$elemMatch": {"service_id": service_id, "used": item["used"]}}},
                                              {"$inc": {"items.$.used": 1}, "$push": {"uses": use}})
    if not res.modified_count:
        raise HTTPException(409, "El paquete cambió, intente de nuevo")
    cp = await one("client_packages", {"id": cp["id"]})
    left_item, left = item["qty"] - item["used"] - 1, remaining(cp)
    if left == 0:
        await wa_send(cid, cp["client_phone"], f"Usó la última sesión de su paquete {cp['name']}. ¡Gracias por su preferencia! Pregúntenos por un nuevo paquete.", "bot")
    elif left_item == 1:
        await wa_send(cid, cp["client_phone"], f"Le queda 1 sesión de {item['service_name']} en su paquete {cp['name']} (vence el {cp['expires']}).", "bot")
    return cp, use


async def unconsume(appointment_id):
    cp = await one("client_packages", {"uses.appointment_id": appointment_id})
    if not cp:
        return
    use = next(u for u in cp["uses"] if u.get("appointment_id") == appointment_id)
    await db.client_packages.update_one({"id": cp["id"], "items.service_id": use["service_id"]},
                                        {"$inc": {"items.$.used": -1}, "$pull": {"uses": {"id": use["id"]}}})


@r.post("/client-packages")
async def sell(body: dict = Body(...), c=Depends(guard(STAFF))):
    from routes_extra import check_payments
    cl = await one("clients", {"id": body.get("client_id"), "company_id": c["cid"]})
    p = await one("packages", {"id": body.get("package_id"), "company_id": c["cid"]})
    if not cl or not p or p.get("active") is False:
        raise HTTPException(400, "Seleccione la clienta y un paquete activo")
    pays = check_payments(body.get("payments") or [], p["price"])
    branch = await one("branches", {"id": body.get("branch_id"), "company_id": c["cid"]}) or {}
    cpid, sid, total = uid(), uid(), sum(i["qty"] for i in p["items"])
    sale = {"id": sid, "company_id": c["cid"], "kind": "package", "client_package_id": cpid, "branch_id": branch.get("id"),
            "branch_name": branch.get("name", ""), "stylist_id": None, "stylist_name": "Mostrador", "client_name": cl["name"],
            "description": f"Paquete {p['name']}", "date": today(), "subtotal": p["price"], "discount": 0, "tip": 0, "deposit_applied": 0,
            "net": p["price"], "payments": pays, "total": p["price"], "commission": 0, "created_by": c["user"]["email"], "voided": False, "created_at": now_iso()}
    expires = (datetime.strptime(today(), "%Y-%m-%d") + timedelta(days=p["validity_days"])).strftime("%Y-%m-%d")
    cp = {"id": cpid, "company_id": c["cid"], "client_id": cl["id"], "client_name": cl["name"], "client_phone": cl["phone"],
          "package_id": p["id"], "name": p["name"], "items": [{**i, "used": 0} for i in p["items"]], "price": p["price"],
          "unit_value": round(p["price"] / total, 2), "sold_at": today(), "expires": expires, "status": "active", "sale_id": sid,
          "uses": [], "sold_by": c["user"]["email"], "created_at": now_iso()}
    await insert("sales", sale)
    await insert("client_packages", cp)
    detail = ", ".join(f"{i['qty']} x {i['service_name']}" for i in p["items"])
    await wa_send(c["cid"], cl["phone"], f"¡Gracias por su compra! Su paquete {p['name']} ({detail}) está activo hasta el {expires}. "
                  "Al venir a su cita se descontará automáticamente.", "confirmation")
    await audit(c["user"], c["cid"], "sell", "client_package", f"{cl['name']} {p['name']} Q{p['price']}")
    return view(cp)


@r.get("/client-packages")
async def list_cps(client_id: str = "", status: str = "", c=Depends(guard(ALL_STAFF))):
    q = {"company_id": c["cid"], **({"client_id": client_id} if client_id else {})}
    out = [view(x) for x in await find("client_packages", q, [("created_at", -1)], 1000)]
    return [x for x in out if not status or x["status"] == status]


@r.get("/client-packages/report")
async def report(c=Depends(guard(STAFF))):
    rows = [view(x) for x in await find("client_packages", {"company_id": c["cid"]})]
    ok = [x for x in rows if x["status"] != "voided"]
    by = {}
    for x in ok:
        b = by.setdefault(x["name"], {"name": x["name"], "sold": 0, "revenue": 0, "used": 0, "remaining": 0})
        b["sold"] += 1
        b["revenue"] = round(b["revenue"] + x["price"], 2)
        b["used"] += x["total"] - x["remaining"]
        b["remaining"] += x["remaining"] if x["status"] == "active" else 0
    return {"sold": len(ok), "revenue": round(sum(x["price"] for x in ok), 2), "active": sum(1 for x in ok if x["status"] == "active"),
            "used": sum(x["total"] - x["remaining"] for x in ok), "pending": sum(x["remaining"] for x in ok if x["status"] == "active"),
            "expired": sum(1 for x in ok if x["status"] == "expired"), "lost": sum(x["remaining"] for x in ok if x["status"] == "expired"),
            "by_package": sorted(by.values(), key=lambda b: -b["revenue"])}


@r.post("/client-packages/{oid}/use")
async def use_session(oid: str, body: dict = Body(...), c=Depends(guard(STAFF))):
    cp = await get_cp(c, oid)
    cp, _ = await consume(c["cid"], cp, body.get("service_id"), c["user"], note=(body.get("note") or "").strip())
    await audit(c["user"], c["cid"], "use", "client_package", f"{cp['client_name']} {cp['name']} {body.get('service_id')}")
    return view(cp)


@r.post("/client-packages/{oid}/void")
async def void_cp(oid: str, body: dict = Body(default={}), c=Depends(guard(OWNER))):
    cp = await get_cp(c, oid)
    if cp["status"] == "voided":
        raise HTTPException(400, "El paquete ya está anulado")
    if cp["uses"]:
        raise HTTPException(400, "No se puede anular: ya tiene sesiones usadas")
    await db.client_packages.update_one({"id": oid}, {"$set": {"status": "voided", "void_reason": body.get("reason", "")}})
    await db.sales.update_one({"id": cp["sale_id"]}, {"$set": {"voided": True, "void_reason": body.get("reason", ""), "voided_by": c["user"]["email"]}})
    await audit(c["user"], c["cid"], "void", "client_package", f"{oid} {body.get('reason', '')}")
    return {"ok": True}


def find_membership(company, cl):
    name = (cl or {}).get("membership", "").strip().lower()
    mems = company.get("settings", {}).get("loyalty", {}).get("memberships") or []
    return next(({"name": m["name"], "percent": float(m.get("discount") or 0)} for m in mems
                 if name and m.get("name", "").strip().lower() == name and float(m.get("discount") or 0) > 0), None)


async def find_coupon(cid, code):
    code = (code or "").strip()
    cp = await one("loyalty_coupons", {"company_id": cid, "code": {"$regex": f"^{re.escape(code)}$", "$options": "i"}}) if code else None
    if not cp or float(cp.get("percent") or 0) <= 0:
        raise HTTPException(400, "Cupón no válido")
    if cp.get("expires") and cp["expires"] < today():
        raise HTTPException(400, f"El cupón venció el {cp['expires']}")
    return cp


@r.post("/coupons/check")
async def coupon_check(body: dict = Body(...), c=Depends(guard(ALL_STAFF))):
    cp = await find_coupon(c["cid"], body.get("code"))
    return {"code": cp["code"], "percent": float(cp["percent"]), "description": cp.get("description", "")}


async def service_price(a):
    svc = await one("services", {"id": a["service_id"]}) or {}
    return round(min(float(svc.get("price") or a["price"]), a["price"]), 2)


@r.get("/appointments/{oid}/checkout-options")
async def checkout_options(oid: str, c=Depends(guard(ALL_STAFF))):
    a = await one("appointments", {"id": oid, "company_id": c["cid"]})
    if not a:
        raise HTTPException(404, "Cita no encontrada")
    cl = await one("clients", {"id": a.get("client_id"), "company_id": c["cid"]})
    cps = [view(x) for x in await find("client_packages", {"company_id": c["cid"], "client_id": a.get("client_id")}, [("expires", 1)])]
    usable = [{"id": x["id"], "name": x["name"], "expires": x["expires"], "remaining": remaining(x, a["service_id"])}
              for x in cps if x["status"] == "active" and remaining(x, a["service_id"]) > 0]
    return {"packages": usable, "package_cover": await service_price(a), "membership": find_membership(c["company"], cl)}


async def checkout_promos(c, a, body):
    cp, cover, pct, label, coupon_id = None, 0.0, 0.0, "", None
    if body.get("package_id"):
        cp = await one("client_packages", {"id": body["package_id"], "company_id": c["cid"], "client_id": a.get("client_id")})
        if not cp or state(cp) != "active" or remaining(cp, a["service_id"]) <= 0:
            raise HTTPException(400, "El paquete no tiene sesiones vigentes para este servicio")
        cover = await service_price(a)
    if body.get("apply_membership") and body.get("coupon_code"):
        raise HTTPException(400, "Aplique membresía o cupón, no ambos")
    if body.get("apply_membership"):
        m = find_membership(c["company"], await one("clients", {"id": a.get("client_id")}))
        if not m:
            raise HTTPException(400, "La clienta no tiene una membresía con descuento")
        pct, label = m["percent"], f"Membresía {m['name']} {m['percent']:g}%"
    elif body.get("coupon_code"):
        k = await find_coupon(c["cid"], body["coupon_code"])
        pct, label, coupon_id = float(k["percent"]), f"Cupón {k['code']} {float(k['percent']):g}%", k["id"]
    promo = round((a["price"] - cover) * pct / 100, 2)
    return {"cp": cp, "cover": cover, "promo": promo, "label": label, "coupon_id": coupon_id, "unit_value": float(cp["unit_value"]) if cp else 0}


async def package_notices():
    limit = (datetime.strptime(today(), "%Y-%m-%d") + timedelta(days=7)).strftime("%Y-%m-%d")
    for cp in await find("client_packages", {"status": "active", "expiry_notice": {"$ne": True}, "expires": {"$gte": today(), "$lte": limit}}):
        if remaining(cp) > 0:
            await wa_send(cp["company_id"], cp["client_phone"], f"Su paquete {cp['name']} vence el {cp['expires']} y aún tiene "
                          f"{remaining(cp)} sesión(es). ¡Agende su cita para aprovecharlas!", "reminder")
        await db.client_packages.update_one({"id": cp["id"]}, {"$set": {"expiry_notice": True}})
