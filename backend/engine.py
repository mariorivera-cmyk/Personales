from datetime import datetime, timedelta
from core import db, find, one, uid, now_iso, local_now, today, wa_send, norm_phone, insert

STEP = 30


class BookingError(Exception):
    def __init__(self, msg, alternatives=None):
        super().__init__(msg)
        self.msg = msg
        self.alternatives = alternatives


def m(s):
    h, mi = s.split(":")
    return int(h) * 60 + int(mi)


def valid_hm(s):
    return isinstance(s, str) and len(s) == 5 and s[2] == ":" and s.replace(":", "").isdigit()


def fm(x):
    return f"{x // 60:02d}:{x % 60:02d}"


def weekday(d):
    return str(datetime.strptime(d, "%Y-%m-%d").weekday())


def overlap(a1, a2, b1, b2):
    return a1 < b2 and b1 < a2


def blocked(b, a1, a2):
    if not b.get("start_time"):
        return True
    return overlap(a1, a2, m(b["start_time"]), m(b["end_time"]))


async def day_slots(cid, branch_id, service_id, date, stylist_id=None, exclude=None, extra=0, company=None):
    company = company or await one("companies", {"id": cid})
    if date in company.get("settings", {}).get("holidays", []) or date < today():
        return []
    branch = await one("branches", {"id": branch_id, "company_id": cid})
    svc = await one("services", {"id": service_id, "company_id": cid})
    if not branch or not svc:
        return []
    wd = weekday(date)
    bh = (branch.get("hours") or {}).get(wd)
    if not bh:
        return []
    q = {"company_id": cid, "branch_id": branch_id, "active": {"$ne": False}}
    if stylist_id:
        q["id"] = stylist_id
    stylists = await find("stylists", q)
    auth = svc.get("stylist_ids") or []
    if auth:
        stylists = [s for s in stylists if s["id"] in auth]
    appts = await find("appointments", {"company_id": cid, "date": date, "status": {"$nin": ["cancelled", "no_show"]}})
    appts = [a for a in appts if a["id"] != exclude]
    blocks = await find("blocks", {"company_id": cid, "start_date": {"$lte": date}, "end_date": {"$gte": date}})
    prep, dur, cl = int(svc.get("prep_minutes") or 0), int(svc["duration"]) + extra, int(svc.get("cleanup_minutes") or 0)
    cap = int(branch.get("capacity") or 99)
    branch_appts = [a for a in appts if a["branch_id"] == branch_id]
    nowm = None
    if date == today():
        ln = local_now()
        nowm = ln.hour * 60 + ln.minute
    out = []
    for st in stylists:
        sh = st["hours"].get(wd) if st.get("hours") else bh
        if not sh:
            continue
        o, c = max(m(bh[0]), m(sh[0])), min(m(bh[1]), m(sh[1]))
        mine = [a for a in appts if a["stylist_id"] == st["id"]]
        blks = [b for b in blocks if b.get("stylist_id") == st["id"] or
                (not b.get("stylist_id") and (not b.get("branch_id") or b["branch_id"] == branch_id))]
        t0 = ((o + prep + STEP - 1) // STEP) * STEP
        for t in range(t0, c - dur - cl + 1, STEP):
            a1, a2 = t - prep, t + dur + cl
            if nowm is not None and t <= nowm:
                continue
            if any(overlap(a1, a2, x["occ_start"], x["occ_end"]) for x in mine):
                continue
            if any(blocked(b, a1, a2) for b in blks):
                continue
            if sum(1 for x in branch_appts if overlap(a1, a2, x["occ_start"], x["occ_end"])) >= cap:
                continue
            out.append({"time": fm(t), "stylist_id": st["id"], "stylist_name": st["name"]})
    out.sort(key=lambda x: x["time"])
    return out


async def alternatives(cid, branch_id, service_id, date, time=None, stylist_id=None):
    res = {"same_day": [], "other_stylists": [], "other_branches": [], "next_days": []}
    slots = await day_slots(cid, branch_id, service_id, date)
    mine = [s for s in slots if not stylist_id or s["stylist_id"] == stylist_id]
    if time:
        res["other_stylists"] = [s for s in slots if s["time"] == time and s["stylist_id"] != stylist_id][:5]
        res["same_day"] = sorted(mine, key=lambda s: abs(m(s["time"]) - m(time)))[:6]
    else:
        res["same_day"] = mine[:8]
    for b in await find("branches", {"company_id": cid, "id": {"$ne": branch_id}}):
        bs = await day_slots(cid, b["id"], service_id, date)
        if time:
            bs = [s for s in bs if s["time"] == time] or bs[:2]
        res["other_branches"] += [{**s, "branch_id": b["id"], "branch_name": b["name"]} for s in bs[:3]]
    d = datetime.strptime(date, "%Y-%m-%d")
    for i in range(1, 10):
        nd = (d + timedelta(days=i)).strftime("%Y-%m-%d")
        ns = await day_slots(cid, branch_id, service_id, nd, stylist_id)
        if ns:
            res["next_days"].append({"date": nd, "slots": ns[:4]})
        if len(res["next_days"]) >= 3:
            break
    return res


async def upsert_client(cid, phone, name=None, email=None, referred_by=None):
    phone = norm_phone(phone)
    c = await one("clients", {"company_id": cid, "phone": phone})
    if c:
        return c
    c = {"id": uid(), "company_id": cid, "phone": phone, "name": name or f"Cliente {phone[-4:]}",
         "email": email or "", "birthdate": "", "gender": "", "points": 0, "membership": "",
         "notes": {}, "referred_by": norm_phone(referred_by) if referred_by else "", "created_at": now_iso()}
    await insert("clients", c)
    if referred_by:
        company = await one("companies", {"id": cid})
        bonus = int(company.get("settings", {}).get("loyalty", {}).get("referral_points", 0))
        await db.clients.update_one({"company_id": cid, "phone": c["referred_by"]}, {"$inc": {"points": bonus}})
    return c


def deposit_for(company, svc, minutes, price):
    if float(svc.get("deposit") or 0) > 0:
        return float(svc["deposit"])
    pct = 0
    for r in company.get("settings", {}).get("deposit_rules", []):
        if minutes >= int(r.get("min_minutes", 0)):
            pct = max(pct, float(r.get("percent", 0)))
    return round(price * pct / 100, 2)


async def book(cid, *, branch_id, service_id, date, time, phone, name=None, stylist_id=None, addon_ids=None,
               rec_type=None, source="staff", email=None, referred_by=None):
    if not valid_hm(time) or not isinstance(date, str):
        raise BookingError("Formato de fecha/hora inválido (HH:MM)")
    company = await one("companies", {"id": cid})
    svc = await one("services", {"id": service_id, "company_id": cid})
    if not svc:
        raise BookingError("Servicio no encontrado")
    addons = await find("services", {"company_id": cid, "id": {"$in": addon_ids or []}})
    extra = sum(int(a["duration"]) for a in addons)
    slots = await day_slots(cid, branch_id, service_id, date, stylist_id, extra=extra, company=company)
    match = [s for s in slots if s["time"] == time]
    if not match:
        raise BookingError("Horario no disponible", await alternatives(cid, branch_id, service_id, date, time, stylist_id))
    st = match[0]
    client = await upsert_client(cid, phone, name, email, referred_by)
    branch = await one("branches", {"id": branch_id})
    dur = int(svc["duration"]) + extra
    price = float(svc["price"]) + sum(float(a["price"]) for a in addons)
    start = m(time)
    since = (datetime.now() - timedelta(days=30)).isoformat()
    run = await db.campaign_runs.find_one({"company_id": cid, "client_ids": client["id"], "run_at": {"$gte": since}},
                                          sort=[("run_at", -1)])
    appt = {
        "id": uid(), "company_id": cid, "branch_id": branch_id, "branch_name": branch["name"],
        "stylist_id": st["stylist_id"], "stylist_name": st["stylist_name"], "client_id": client["id"],
        "client_name": client["name"], "client_phone": client["phone"], "service_id": service_id,
        "service_name": svc["name"], "addon_ids": [a["id"] for a in addons], "addon_names": [a["name"] for a in addons],
        "date": date, "time": time, "end_time": fm(start + dur), "duration": dur,
        "occ_start": start - int(svc.get("prep_minutes") or 0), "occ_end": start + dur + int(svc.get("cleanup_minutes") or 0),
        "price": price, "deposit_required": deposit_for(company, svc, dur, price), "deposit_paid": 0,
        "status": "confirmed" if source == "staff" else "pending", "source": source,
        "rec_type": rec_type if addons else None, "campaign_id": run["campaign_id"] if run else None,
        "reminders_sent": [], "created_at": now_iso()}
    await insert("appointments", appt)
    return appt


async def reschedule(cid, appt_id, date, time, stylist_id=None):
    if not valid_hm(time):
        raise BookingError("Formato de hora inválido (HH:MM)")
    a = await one("appointments", {"id": appt_id, "company_id": cid})
    if not a:
        raise BookingError("Cita no encontrada")
    svc = await one("services", {"id": a["service_id"]})
    extra = a["duration"] - int(svc["duration"])
    slots = await day_slots(cid, a["branch_id"], a["service_id"], date, stylist_id, exclude=appt_id, extra=extra)
    match = [s for s in slots if s["time"] == time]
    if not match:
        raise BookingError("Horario no disponible", await alternatives(cid, a["branch_id"], a["service_id"], date, time, stylist_id))
    start = m(time)
    upd = {"date": date, "time": time, "end_time": fm(start + a["duration"]), "stylist_id": match[0]["stylist_id"],
           "stylist_name": match[0]["stylist_name"], "occ_start": start - int(svc.get("prep_minutes") or 0),
           "occ_end": start + a["duration"] + int(svc.get("cleanup_minutes") or 0), "reminders_sent": [],
           "status": "confirmed"}
    await db.appointments.update_one({"id": appt_id}, {"$set": upd})
    await notify_waitlist(cid, a)
    return {**a, **upd}


async def notify_waitlist(cid, appt):
    ws = await find("waitlist", {"company_id": cid, "status": "waiting", "date": appt["date"], "branch_id": appt["branch_id"]})
    for w in ws:
        if w.get("service_id") and w["service_id"] != appt["service_id"]:
            continue
        await wa_send(cid, w["client_phone"], f"¡Buenas noticias {w.get('client_name', '')}! Se liberó un espacio el "
                      f"{appt['date']} a las {appt['time']} para {appt['service_name']}. Responde RESERVAR para tomarlo.", "waitlist")
        await db.waitlist.update_one({"id": w["id"]}, {"$set": {"status": "notified", "notified_at": now_iso(),
                                                                 "offered_time": appt["time"]}})


async def set_status(cid, appt_id, status):
    a = await one("appointments", {"id": appt_id, "company_id": cid})
    if not a:
        raise BookingError("Cita no encontrada")
    await db.appointments.update_one({"id": appt_id}, {"$set": {"status": status, f"{status}_at": now_iso()}})
    if status == "cancelled":
        await notify_waitlist(cid, a)
    if status == "completed" and a["status"] != "completed":
        company = await one("companies", {"id": cid})
        if "loyalty" in company.get("enabled_modules", []):
            per = float(company.get("settings", {}).get("loyalty", {}).get("points_per_100", 10))
            await db.clients.update_one({"id": a["client_id"]}, {"$inc": {"points": int(a["price"] / 100 * per)}})
    return {**a, "status": status}


async def suggestions(cid, service_id):
    rules = await find("upsell_rules", {"company_id": cid, "trigger_service_id": service_id, "active": {"$ne": False}})
    out = []
    for r in rules:
        s = await one("services", {"id": r["suggested_service_id"], "company_id": cid})
        if s:
            out.append({"rule_id": r["id"], "type": r["type"], "message": r.get("message", ""), "service": s})
            await db.rec_offers.insert_one({"company_id": cid, "type": r["type"], "created_at": now_iso()})
    return out


async def recommendations(cid, client_id=None):
    services = {s["id"]: s for s in await find("services", {"company_id": cid})}
    q = {"company_id": cid, "status": "completed"}
    if client_id:
        q["client_id"] = client_id
    appts = await find("appointments", q, [("date", -1)])
    future = {a["client_id"] for a in await find("appointments", {"company_id": cid, "date": {"$gte": today()},
                                                                   "status": {"$in": ["pending", "confirmed"]}})}
    seen, out = set(), []
    td = datetime.strptime(today(), "%Y-%m-%d")
    for a in appts:
        key = (a["client_id"], a["service_id"])
        if key in seen:
            continue
        seen.add(key)
        s = services.get(a["service_id"])
        days = (td - datetime.strptime(a["date"], "%Y-%m-%d")).days
        if s and int(s.get("rebook_days") or 0) and days >= int(s["rebook_days"]) and a["client_id"] not in future:
            out.append({"client_id": a["client_id"], "client_name": a["client_name"], "client_phone": a["client_phone"],
                        "service_id": s["id"], "service_name": s["name"], "days": days,
                        "message": f"Han pasado {days} días desde su último servicio de {s['name']}. Le recomendamos agendar un retoque."})
    return out


async def run_reminders(cid=None):
    ln = local_now()
    q = {"status": {"$in": ["pending", "confirmed"]}, "date": {"$gte": today(), "$lte": (ln + timedelta(days=3)).strftime("%Y-%m-%d")}}
    if cid:
        q["company_id"] = cid
    sent = 0
    for a in await find("appointments", q):
        company = await one("companies", {"id": a["company_id"]})
        if not company or company["status"] == "suspended":
            continue
        hours = company.get("settings", {}).get("reminder_hours", [48, 24, 2])
        hrs = (datetime.strptime(f"{a['date']} {a['time']}", "%Y-%m-%d %H:%M") - ln).total_seconds() / 3600
        pending = [h for h in hours if 0 < hrs <= h and h not in a.get("reminders_sent", [])]
        if not pending:
            continue
        await wa_send(a["company_id"], a["client_phone"],
                      f"Recordatorio ({min(pending)}h): {a['client_name']}, tu cita de {a['service_name']} es el {a['date']} "
                      f"a las {a['time']} en {a['branch_name']} con {a['stylist_name']}. Responde CONFIRMAR, REPROGRAMAR o CANCELAR.",
                      "reminder")
        await db.appointments.update_one({"id": a["id"]}, {"$addToSet": {"reminders_sent": {"$each": pending}}})
        sent += 1
    return sent
