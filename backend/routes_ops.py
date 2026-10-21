import base64
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Body, HTTPException, UploadFile, File, Form, Response
from core import (db, find, one, uid, now_iso, today, insert, clean, audit, hash_pw, guard, ctx, enc, dec, wa_send,
                  email_send, MANAGERS, STAFF, ALL_STAFF, norm_phone, valid_phone)
import engine as E

r = APIRouter(prefix="/api")


def crud(name, coll, write=("company_admin",), mod=None, create=True, before=None, after=None, validate=None):
    @r.get(f"/{name}", name=f"list_{name}")
    async def _list(c=Depends(guard(None, mod))):
        return await find(coll, {"company_id": c["cid"]}, [("created_at", 1)])

    if create:
        @r.post(f"/{name}", name=f"create_{name}")
        async def _create(body: dict = Body(...), c=Depends(guard(write, mod))):
            if before:
                await before(c, body)
            if validate:
                await validate(c, body, False)
            doc = {**clean(body), "id": uid(), "company_id": c["cid"], "created_at": now_iso()}
            await audit(c["user"], c["cid"], "create", name, doc.get("name", doc["id"]))
            out = await insert(coll, doc)
            if after:
                await after(c, out)
            return out

    @r.put(f"/{name}/{{oid}}", name=f"update_{name}")
    async def _update(oid: str, body: dict = Body(...), c=Depends(guard(write, mod))):
        if validate:
            await validate(c, body, True)
        await db[coll].update_one({"id": oid, "company_id": c["cid"]}, {"$set": clean(body)})
        await audit(c["user"], c["cid"], "update", name, oid)
        out = await one(coll, {"id": oid})
        if after and out:
            await after(c, out)
        return out

    @r.delete(f"/{name}/{{oid}}", name=f"delete_{name}")
    async def _delete(oid: str, c=Depends(guard(write, mod))):
        await db[coll].delete_one({"id": oid, "company_id": c["cid"]})
        await audit(c["user"], c["cid"], "delete", name, oid)
        return {"ok": True}


async def branch_limit(c, body):
    n = await db.branches.count_documents({"company_id": c["cid"]})
    if n >= 1 and "multi_branch" not in c["company"].get("enabled_modules", []):
        raise HTTPException(403, "Habilite el módulo Multi-sucursal para agregar más sucursales")


async def stylist_services_sync(c, st):
    for sid in st.get("service_ids") or []:
        await db.services.update_one({"id": sid, "company_id": c["cid"], "stylist_ids.0": {"$exists": True}}, {"$addToSet": {"stylist_ids": st["id"]}})


crud("branches", "branches", before=branch_limit)
crud("stylists", "stylists", write=MANAGERS, after=stylist_services_sync)
crud("services", "services")
crud("blocks", "blocks", write=MANAGERS)
crud("rules", "upsell_rules", mod="upsell")
crud("campaigns", "campaigns", mod="marketing")
crud("coupons", "loyalty_coupons", mod="loyalty")
crud("waitlist", "waitlist", write=STAFF, mod="waitlist", create=False)


@r.post("/waitlist")
async def add_waitlist(body: dict = Body(...), c=Depends(guard(STAFF, "waitlist"))):
    return await waitlist_entry(c["cid"], body)


async def waitlist_entry(cid, body):
    cl = await E.upsert_client(cid, body["phone"], body.get("name"))
    svc = await one("services", {"id": body.get("service_id")}) or {}
    return await insert("waitlist", {"id": uid(), "company_id": cid, "client_id": cl["id"], "client_name": cl["name"],
                                     "client_phone": cl["phone"], "service_id": body.get("service_id"), "service_name": svc.get("name", ""),
                                     "branch_id": body.get("branch_id"), "date": body.get("date"), "notes": body.get("notes", ""),
                                     "status": "waiting", "created_at": now_iso()})


@r.get("/company")
async def get_company(c=Depends(ctx)):
    return c["company"]


@r.put("/company")
async def put_company(body: dict = Body(...), c=Depends(guard(("company_admin",)))):
    upd = {k: v for k, v in body.items() if k in ("name", "phone", "whatsapp_number", "slug", "logo", "address", "description", "logo_url",
                                                "photo_urls", "social", "show_team")}
    if "whatsapp_number" in upd:
        upd["whatsapp_number"] = norm_phone(upd["whatsapp_number"])
    if "settings" in body:
        upd["settings"] = {**c["company"].get("settings", {}), **body["settings"]}
    await db.companies.update_one({"id": c["cid"]}, {"$set": upd})
    await audit(c["user"], c["cid"], "update", "company_settings", list(upd.keys()))
    return await one("companies", {"id": c["cid"]})


# ---------- Users ----------
@r.get("/users")
async def list_users(c=Depends(guard(MANAGERS))):
    return await find("users", {"company_id": c["cid"]}) if True else []


@r.post("/users")
async def create_user(body: dict = Body(...), c=Depends(guard(("company_admin",)))):
    if body.get("role") not in ("company_admin", "branch_manager", "receptionist", "stylist"):
        raise HTTPException(400, "Rol inválido")
    email = body["email"].strip().lower()
    if await one("users", {"email": email}):
        raise HTTPException(400, "El correo ya existe")
    u = {"id": uid(), "email": email, "name": body.get("name", ""), "role": body["role"], "company_id": c["cid"],
         "branch_id": body.get("branch_id"), "stylist_id": body.get("stylist_id"), "active": True, "created_at": now_iso()}
    await db.users.insert_one({**u, "password_hash": hash_pw(body["password"])})
    await audit(c["user"], c["cid"], "create", "user", email)
    return u


@r.put("/users/{oid}")
async def update_user(oid: str, body: dict = Body(...), c=Depends(guard(("company_admin",)))):
    upd = {k: v for k, v in body.items() if k in ("name", "role", "branch_id", "stylist_id", "active")}
    if body.get("password"):
        upd["password_hash"] = hash_pw(body["password"])
    await db.users.update_one({"id": oid, "company_id": c["cid"]}, {"$set": upd})
    await audit(c["user"], c["cid"], "update", "user", oid)
    return await db.users.find_one({"id": oid}, {"_id": 0, "password_hash": 0})


@r.delete("/users/{oid}")
async def delete_user(oid: str, c=Depends(guard(("company_admin",)))):
    await db.users.delete_one({"id": oid, "company_id": c["cid"], "role": {"$ne": "super_admin"}})
    await audit(c["user"], c["cid"], "delete", "user", oid)
    return {"ok": True}


@r.get("/audit")
async def get_audit(c=Depends(guard(("company_admin",)))):
    return await find("audit_logs", {"company_id": c["cid"]}, [("created_at", -1)], 300)


# ---------- Clients (CRM) ----------
def client_out(cl):
    n = cl.get("notes") or {}
    return {**cl, "notes": {k: dec(v) for k, v in n.items()}}


@r.get("/clients")
async def list_clients(q: str = "", c=Depends(guard(ALL_STAFF))):
    query = {"company_id": c["cid"]}
    if q:
        query["$or"] = [{"name": {"$regex": q, "$options": "i"}}, {"phone": {"$regex": q.replace("+", "")}}]
    clients = await find("clients", query, [("name", 1)], 1000)
    return [{k: v for k, v in x.items() if k != "notes"} for x in clients]


@r.post("/clients")
async def create_client(body: dict = Body(...), c=Depends(guard(STAFF))):
    if not valid_phone(body.get("phone")):
        raise HTTPException(400, "Teléfono inválido: incluya el código de país y el número completo")
    cl = await E.upsert_client(c["cid"], body["phone"], body.get("name"), body.get("email"), body.get("referred_by"))
    upd = {k: body[k] for k in ("birthdate", "gender", "email") if body.get(k)}
    if upd:
        await db.clients.update_one({"id": cl["id"]}, {"$set": upd})
    await audit(c["user"], c["cid"], "create", "client", cl["phone"])
    return client_out(await one("clients", {"id": cl["id"]}))


@r.get("/clients/{oid}")
async def client_detail(oid: str, c=Depends(guard(ALL_STAFF))):
    cl = await one("clients", {"id": oid, "company_id": c["cid"]})
    if not cl:
        raise HTTPException(404, "Cliente no encontrado")
    appts = await find("appointments", {"client_id": oid}, [("date", -1)])
    done = [a for a in appts if a["status"] == "completed"]
    dates = sorted(datetime.strptime(a["date"], "%Y-%m-%d") for a in done)
    freq = round(sum((dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)) / (len(dates) - 1)) if len(dates) > 1 else None
    files = await db.client_files.find({"client_id": oid}, {"_id": 0, "data": 0}).to_list(100)
    await audit(c["user"], c["cid"], "view", "client_file", cl["name"])
    return {"client": client_out(cl), "appointments": appts, "files": files,
            "stats": {"visits": len(done), "spent": sum(a["price"] for a in done), "frequency_days": freq,
                      "cancellations": sum(1 for a in appts if a["status"] == "cancelled"),
                      "late_cancels": sum(1 for a in appts if a.get("late_cancel")),
                      "no_shows": sum(1 for a in appts if a["status"] == "no_show"),
                      "future": sum(1 for a in appts if a["date"] >= today() and a["status"] in ("pending", "confirmed")),
                      "last_visit": done[0]["date"] if done else None},
            "recommendations": await E.recommendations(c["cid"], oid)}


@r.put("/clients/{oid}")
async def update_client(oid: str, body: dict = Body(...), c=Depends(guard(ALL_STAFF))):
    upd = {k: v for k, v in body.items() if k in ("name", "email", "birthdate", "gender", "membership", "no_whatsapp", "photo_consent", "data_consent")}
    if "notes" in body:
        upd["notes"] = {k: enc(v) for k, v in body["notes"].items()}
    await db.clients.update_one({"id": oid, "company_id": c["cid"]}, {"$set": upd})
    await audit(c["user"], c["cid"], "update", "client", oid)
    return client_out(await one("clients", {"id": oid}))


@r.post("/clients/{oid}/files")
async def upload_file(oid: str, file: UploadFile = File(...), kind: str = Form("documento"), appointment_id: str = Form(""), c=Depends(guard(ALL_STAFF))):
    cl = await one("clients", {"id": oid, "company_id": c["cid"]})
    if kind in ("foto", "antes", "despues") and cl and cl.get("photo_consent") is False:
        raise HTTPException(400, "La clienta no autorizó fotografías")
    data = await file.read()
    if len(data) > 3 * 1024 * 1024:
        raise HTTPException(400, "Archivo máximo 3MB")
    doc = {"id": uid(), "company_id": c["cid"], "client_id": oid, "name": file.filename, "kind": kind,
           "content_type": file.content_type, "size": len(data), "appointment_id": appointment_id, "created_at": now_iso()}
    await db.client_files.insert_one({**doc, "data": base64.b64encode(data).decode()})
    await audit(c["user"], c["cid"], "upload", "client_file", file.filename)
    return doc


@r.get("/files/{fid}")
async def get_file(fid: str, c=Depends(guard(ALL_STAFF))):
    f = await one("client_files", {"id": fid, "company_id": c["cid"]})
    if not f:
        raise HTTPException(404, "Archivo no encontrado")
    return Response(base64.b64decode(f["data"]), media_type=f["content_type"] or "application/octet-stream",
                    headers={"Content-Disposition": f"inline; filename={f['name']}"})


@r.delete("/files/{fid}")
async def del_file(fid: str, c=Depends(guard(STAFF))):
    await db.client_files.delete_one({"id": fid, "company_id": c["cid"]})
    return {"ok": True}


# ---------- Appointments ----------
@r.get("/appointments")
async def list_appts(start: str = "", end: str = "", branch_id: str = "", stylist_id: str = "", c=Depends(guard(ALL_STAFF))):
    q = {"company_id": c["cid"]}
    if start:
        q["date"] = {"$gte": start, "$lte": end or start}
    u = c["user"]
    if u["role"] == "stylist":
        q["stylist_id"] = u.get("stylist_id") or "-"
    elif u["role"] == "branch_manager":
        q["branch_id"] = u.get("branch_id") or "-"
    if branch_id:
        q["branch_id"] = branch_id
    if stylist_id and u["role"] != "stylist":
        q["stylist_id"] = stylist_id
    return await find("appointments", q, [("date", 1), ("time", 1)])


@r.get("/availability")
async def availability(branch_id: str, service_id: str, date: str, stylist_id: str = "", c=Depends(guard(ALL_STAFF))):
    slots = await E.day_slots(c["cid"], branch_id, service_id, date, stylist_id or None)
    alts = None if slots else await E.alternatives(c["cid"], branch_id, service_id, date, None, stylist_id or None)
    return {"slots": slots, "alternatives": alts}


@r.get("/suggestions")
async def get_suggestions(service_id: str, c=Depends(guard(ALL_STAFF))):
    if "upsell" not in c["company"].get("enabled_modules", []):
        return []
    return await E.suggestions(c["cid"], service_id)


def booking_error(e):
    raise HTTPException(409, {"message": e.msg, "alternatives": e.alternatives})


@r.post("/appointments")
async def create_appt(body: dict = Body(...), c=Depends(guard(STAFF))):
    try:
        a = await E.book(c["cid"], branch_id=body["branch_id"], service_id=body["service_id"], date=body["date"], time=body["time"],
                         phone=body["phone"], name=body.get("name"), stylist_id=body.get("stylist_id") or None,
                         addon_ids=body.get("addon_ids"), rec_type=body.get("rec_type"), source="staff")
    except E.BookingError as e:
        booking_error(e)
    await wa_send(c["cid"], a["client_phone"], f"Tu cita de {a['service_name']} quedó agendada el {a['date']} a las {a['time']} en {a['branch_name']}.", "confirmation")
    await audit(c["user"], c["cid"], "create", "appointment", a["id"])
    return a


@r.post("/appointments/{oid}/status")
async def appt_status(oid: str, body: dict = Body(...), c=Depends(guard(ALL_STAFF))):
    st = body.get("status")
    if st not in ("pending", "confirmed", "in_progress", "completed", "cancelled", "no_show"):
        raise HTTPException(400, "Estado inválido")
    try:
        a = await E.set_status(c["cid"], oid, st, c["user"], body.get("reason", ""), apply_policy=bool(body.get("apply_policy")))
    except E.BookingError as e:
        booking_error(e)
    await audit(c["user"], c["cid"], "status", "appointment", f"{oid} -> {st}" + (f" ({a.get('cancel_type')})" if st == "cancelled" else ""))
    return a


@r.get("/appointments/{oid}/cancel-preview")
async def cancel_preview(oid: str, c=Depends(guard(ALL_STAFF))):
    a = await one("appointments", {"id": oid, "company_id": c["cid"]})
    if not a:
        raise HTTPException(404, "Cita no encontrada")
    return E.cancel_preview(a, await E.appt_rules(a, c["company"]))


@r.post("/appointments/{oid}/reschedule")
async def appt_reschedule(oid: str, body: dict = Body(...), c=Depends(guard(STAFF))):
    try:
        a = await E.reschedule(c["cid"], oid, body["date"], body["time"], body.get("stylist_id") or None)
    except E.BookingError as e:
        booking_error(e)
    await audit(c["user"], c["cid"], "reschedule", "appointment", oid)
    return a


@r.post("/reminders/run")
async def reminders(c=Depends(guard(STAFF))):
    return {"sent": await E.run_reminders(c["cid"])}


# ---------- Dashboard & Reports ----------
@r.get("/dashboard")
async def dashboard(c=Depends(guard(STAFF))):
    cid, td = c["cid"], today()
    ms = td[:8] + "01"
    q = {"company_id": cid}
    if c["user"]["role"] == "branch_manager":
        q["branch_id"] = c["user"].get("branch_id")
    appts = await find("appointments", q)
    month = [a for a in appts if a["date"] >= ms]
    done = [a for a in month if a["status"] == "completed"]
    todays = [a for a in appts if a["date"] == td]
    sales = sum(a.get("paid_net", a["price"]) for a in done)
    wd = E.weekday(td)
    avail = 0
    for b in await find("branches", {"company_id": cid}):
        bh = (b.get("hours") or {}).get(wd)
        if not bh:
            continue
        for st in await find("stylists", {"company_id": cid, "branch_id": b["id"], "active": {"$ne": False}}):
            sh = st["hours"].get(wd) if st.get("hours") else bh
            if sh:
                avail += max(0, min(E.m(bh[1]), E.m(sh[1])) - max(E.m(bh[0]), E.m(sh[0])))
    booked = sum(a["duration"] for a in todays if a["status"] not in ("cancelled", "no_show"))
    counts = {}
    for a in appts:
        if a["status"] == "completed":
            counts[a["client_id"]] = counts.get(a["client_id"], 0) + 1
    runs = await find("campaign_runs", {"company_id": cid, "run_at": {"$gte": ms}})
    sent = sum(x["sent"] for x in runs)
    offers = {t: await db.rec_offers.count_documents({"company_id": cid, "type": t}) for t in ("cross", "up")}
    conv = {t: sum(1 for a in appts if a.get("rec_type") == t) for t in ("cross", "up")}
    series = []
    for i in range(13, -1, -1):
        d = (datetime.strptime(td, "%Y-%m-%d") - timedelta(days=i)).strftime("%Y-%m-%d")
        series.append({"date": d[5:], "ventas": sum(a.get("paid_net", a["price"]) for a in appts if a["date"] == d and a["status"] == "completed"),
                       "citas": sum(1 for a in appts if a["date"] == d)})
    return {"today": len(todays), "today_list": sorted(todays, key=lambda a: a["time"]),
            "future": sum(1 for a in appts if a["date"] > td and a["status"] in ("pending", "confirmed")),
            "occupancy": round(booked / avail * 100, 1) if avail else 0, "available_hours": round(max(avail - booked, 0) / 60, 1),
            "sales": sales, "avg_ticket": round(sales / len(done), 2) if done else 0,
            "new_clients": await db.clients.count_documents({"company_id": cid, "created_at": {"$gte": ms}}),
            "recurring_clients": sum(1 for v in counts.values() if v >= 2),
            "campaign_conv": round(sum(1 for a in month if a.get("campaign_id")) / sent * 100, 1) if sent else 0,
            "cross_conv": round(conv["cross"] / offers["cross"] * 100, 1) if offers["cross"] else 0,
            "up_conv": round(conv["up"] / offers["up"] * 100, 1) if offers["up"] else 0,
            "series": series, "currency": c["company"].get("currency", "GTQ")}


@r.get("/reports")
async def reports(group: str = "branch", start: str = "", end: str = "", c=Depends(guard(MANAGERS, "reports_adv"))):
    key = {"branch": "branch_name", "stylist": "stylist_name", "service": "service_name", "client": "client_name"}.get(group, "branch_name")
    q = {"company_id": c["cid"]}
    if start:
        q["date"] = {"$gte": start, "$lte": end or today()}
    costs = {s["id"]: float(s.get("cost") or 0) for s in await find("services", {"company_id": c["cid"]})}
    rows = {}
    for a in await find("appointments", q):
        k = a.get(key) or "-"
        x = rows.setdefault(k, {"name": k, "total": 0, "completed": 0, "cancelled": 0, "no_show": 0, "sales": 0, "cost": 0, "minutes": 0})
        x["total"] += 1
        if a["status"] in ("completed", "cancelled", "no_show"):
            x[a["status"]] += 1
        if a["status"] == "completed":
            x["sales"] += a.get("paid_net", a["price"])
            x["cost"] += costs.get(a["service_id"], 0)
            x["minutes"] += a["duration"]
    out = []
    for x in rows.values():
        x["margin"] = round(x["sales"] - x["cost"], 2)
        x["effectiveness"] = round(x["completed"] / x["total"] * 100, 1) if x["total"] else 0
        x["hours"] = round(x.pop("minutes") / 60, 1)
        out.append(x)
    return sorted(out, key=lambda x: -x["sales"])


# ---------- Loyalty ----------
@r.get("/loyalty")
async def loyalty(c=Depends(guard(STAFF, "loyalty"))):
    top = await find("clients", {"company_id": c["cid"]}, [("points", -1)], 20)
    import rules as R
    ru = R.effective(c["company"])
    return {"config": {**c["company"].get("settings", {}).get("loyalty", {}), "points_per_100": ru["loyalty_points_per_100"],
                       "redeem_value": ru["loyalty_redeem_value"]},
            "top": [{k: x.get(k) for k in ("id", "name", "phone", "points", "membership", "referred_by")} for x in top]}


@r.put("/loyalty")
async def put_loyalty(body: dict = Body(...), c=Depends(guard(("company_admin",), "loyalty"))):
    import rules as R
    vals = {k2: body.pop(k1) for k1, k2 in (("points_per_100", "loyalty_points_per_100"), ("redeem_value", "loyalty_redeem_value")) if k1 in body}
    if vals:
        await R.save_rules(c, vals)
    await db.companies.update_one({"id": c["cid"]}, {"$set": {"settings.loyalty": body}})
    return body


@r.post("/loyalty/points")
async def loyalty_points(body: dict = Body(...), c=Depends(guard(STAFF, "loyalty"))):
    cl = await one("clients", {"id": body["client_id"], "company_id": c["cid"]})
    pts = int(body["points"])
    if body.get("redeem"):
        if pts > cl.get("points", 0):
            raise HTTPException(400, "Puntos insuficientes")
        pts = -pts
    await db.clients.update_one({"id": cl["id"]}, {"$inc": {"points": pts}})
    import rules as R
    value = round(abs(pts) * float(R.effective(c["company"])["loyalty_redeem_value"]), 2) if pts < 0 else 0
    await audit(c["user"], c["cid"], "points", "client", f"{cl['name']} {pts}")
    return {"points": cl.get("points", 0) + pts, "value": value}


# ---------- Recommendations & campaigns ----------
@r.get("/recommendations")
async def get_recs(c=Depends(guard(STAFF))):
    return await E.recommendations(c["cid"])


@r.post("/campaigns/{oid}/run")
async def run_campaign(oid: str, c=Depends(guard(("company_admin",), "marketing"))):
    camp = await one("campaigns", {"id": oid, "company_id": c["cid"]})
    clients = await find("clients", {"company_id": c["cid"]})
    last = {}
    for a in await find("appointments", {"company_id": c["cid"], "status": "completed"}):
        last[a["client_id"]] = max(last.get(a["client_id"], ""), a["date"])
    td = datetime.strptime(today(), "%Y-%m-%d")
    days = lambda cl: (td - datetime.strptime(last[cl["id"]], "%Y-%m-%d")).days if cl["id"] in last else 9999
    t, n = camp["type"], int(camp.get("days") or 60)
    if t == "birthday":
        soon = {(td + timedelta(days=i)).strftime("%m-%d") for i in range(7)}
        targets = [x for x in clients if x.get("birthdate") and x["birthdate"][5:] in soon]
    elif t == "inactive":
        targets = [x for x in clients if n <= days(x) < 9999]
    elif t == "recovery":
        targets = [x for x in clients if days(x) >= max(n, 120) and days(x) < 9999]
    elif t == "retouch":
        ids = {x["client_id"] for x in await E.recommendations(c["cid"])}
        targets = [x for x in clients if x["id"] in ids]
    else:
        targets = clients
    for x in targets:
        text = (camp.get("message") or "").replace("{nombre}", x["name"]).replace("{salon}", c["company"]["name"])
        if camp.get("channel", "whatsapp") == "email":
            await email_send(c["cid"], x.get("email"), camp["name"], text)
        else:
            await wa_send(c["cid"], x["phone"], text, "campaign")
    await insert("campaign_runs", {"id": uid(), "company_id": c["cid"], "campaign_id": oid, "sent": len(targets),
                                   "client_ids": [x["id"] for x in targets], "run_at": now_iso()})
    await db.campaigns.update_one({"id": oid}, {"$set": {"last_run": now_iso()}, "$inc": {"sent_total": len(targets)}})
    return {"sent": len(targets)}
