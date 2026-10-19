from datetime import datetime, timedelta
from core import (db, find, one, uid, now_iso, local_now, today, wa_send, norm_phone, insert, valid_phone, portal_url, fill,
                  notify_company, email_send)
import rules as R

DEFAULT_REMINDER = ("Recordatorio: {nombre}, su cita de {servicio} es el {fecha} a las {hora} con {estilista} en {sucursal} "
                    "({direccion}). Responda CONFIRMAR, REPROGRAMAR o CANCELAR, o gestione su cita aquí: {enlace}")


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


def intervals(a):
    if a.get("pause"):
        return [(a["occ_start"], a["pause"][0]), (a["pause"][1], a["occ_end"])]
    return [(a["occ_start"], a["occ_end"])]


def cleanup_of(svc, rules):
    return int(svc["cleanup_minutes"]) if svc.get("cleanup_minutes") not in (None, "") else int(rules["default_cleanup_min"])


def ceil_step(x, step):
    return ((x + step - 1) // step) * step


def overlap(a1, a2, b1, b2):
    return a1 < b2 and b1 < a2


def blocked(b, a1, a2):
    if not b.get("start_time"):
        return True
    return overlap(a1, a2, m(b["start_time"]), m(b["end_time"]))


async def day_slots(cid, branch_id, service_id, date, stylist_id=None, exclude=None, extra=0, company=None, public=False):
    company = company or await one("companies", {"id": cid})
    if date in company.get("settings", {}).get("holidays", []) or date < today():
        return []
    rules = R.effective(company, branch_id)
    step = int(rules["slot_interval"])
    earliest = None
    if public:
        if date > (local_now() + timedelta(days=int(rules["max_advance_days"]))).strftime("%Y-%m-%d"):
            return []
        earliest = local_now() + timedelta(hours=float(rules["min_advance_hours"]))
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
    stylists = [s for s in stylists if not s.get("service_ids") or svc["id"] in s["service_ids"]]
    appts = await find("appointments", {"company_id": cid, "date": date, "status": {"$nin": ["cancelled", "no_show"]}})
    appts = [a for a in appts if a["id"] != exclude]
    blocks = await find("blocks", {"company_id": cid, "start_date": {"$lte": date}, "end_date": {"$gte": date}})
    prep, dur = int(svc.get("prep_minutes") or 0), int(svc["duration"]) + extra
    cl = cleanup_of(svc, rules)
    ps, pm = int(svc.get("pause_start") or 0), int(svc.get("pause_minutes") or 0)
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
        t0 = ceil_step(o + prep, step)
        for t in range(t0, c - dur - cl + 1, step):
            a1, a2 = t - prep, t + dur + cl
            if nowm is not None and t <= nowm:
                continue
            if earliest and datetime.strptime(date, "%Y-%m-%d") + timedelta(minutes=t) < earliest:
                continue
            cand = [(a1, t + ps), (t + ps + pm, a2)] if pm else [(a1, a2)]
            if any(overlap(c1, c2, i1, i2) for x in mine for c1, c2 in cand for i1, i2 in intervals(x)):
                continue
            if any(blocked(b, a1, a2) for b in blks):
                continue
            if sum(1 for x in branch_appts if overlap(a1, a2, x["occ_start"], x["occ_end"])) >= cap:
                continue
            out.append({"time": fm(t), "stylist_id": st["id"], "stylist_name": st["name"]})
    out.sort(key=lambda x: x["time"])
    return out


async def alternatives(cid, branch_id, service_id, date, time=None, stylist_id=None, public=False):
    res = {"same_day": [], "other_stylists": [], "other_branches": [], "next_days": []}
    slots = await day_slots(cid, branch_id, service_id, date, public=public)
    mine = [s for s in slots if not stylist_id or s["stylist_id"] == stylist_id]
    if time:
        res["other_stylists"] = [s for s in slots if s["time"] == time and s["stylist_id"] != stylist_id][:5]
        res["same_day"] = sorted(mine, key=lambda s: abs(m(s["time"]) - m(time)))[:6]
    else:
        res["same_day"] = mine[:8]
    for b in await find("branches", {"company_id": cid, "id": {"$ne": branch_id}}):
        bs = await day_slots(cid, b["id"], service_id, date, public=public)
        if time:
            bs = [s for s in bs if s["time"] == time] or bs[:2]
        res["other_branches"] += [{**s, "branch_id": b["id"], "branch_name": b["name"]} for s in bs[:3]]
    d = datetime.strptime(date, "%Y-%m-%d")
    for i in range(1, 10):
        nd = (d + timedelta(days=i)).strftime("%Y-%m-%d")
        ns = await day_slots(cid, branch_id, service_id, nd, stylist_id, public=public)
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


async def client_guard(cid, client, rules, group_id=None):
    faults = await R.fault_count(client["id"], rules) if rules["noshow_enabled"] else 0
    over = rules["noshow_enabled"] and faults >= int(rules["noshow_limit"])
    if over and rules["noshow_action"] == "block":
        raise BookingError("No es posible reservar en línea. Comuníquese con el salón para agendar su cita.")
    if group_id and await db.appointments.count_documents({"group_id": group_id}):
        return over
    active = await find("appointments", {"company_id": cid, "client_id": client["id"], "date": {"$gte": today()},
                                         "status": {"$in": ["pending", "confirmed"]}})
    visits = {a.get("group_id") or a["id"] for a in active}
    if len(visits) >= int(rules["max_active_per_client"]):
        raise BookingError(f"Ya tiene {len(visits)} citas activas; el máximo permitido es {rules['max_active_per_client']}. "
                           "Cancele o espere a una de ellas para reservar otra.")
    return over


async def book(cid, *, branch_id, service_id, date, time, phone, name=None, stylist_id=None, addon_ids=None,
               rec_type=None, source="staff", email=None, referred_by=None, group_id=None):
    if not valid_phone(phone):
        raise BookingError("Teléfono inválido: incluya el código de país y el número completo")
    if not valid_hm(time) or not isinstance(date, str):
        raise BookingError("Formato de fecha/hora inválido (HH:MM)")
    company = await one("companies", {"id": cid})
    svc = await one("services", {"id": service_id, "company_id": cid})
    if not svc:
        raise BookingError("Servicio no encontrado")
    public = source != "staff"
    rules = R.effective(company, branch_id)
    addons = await find("services", {"company_id": cid, "id": {"$in": addon_ids or []}})
    extra = sum(int(a["duration"]) for a in addons)
    slots = await day_slots(cid, branch_id, service_id, date, stylist_id, extra=extra, company=company, public=public)
    match = [s for s in slots if s["time"] == time]
    if not match:
        raise BookingError("Horario no disponible", await alternatives(cid, branch_id, service_id, date, time, stylist_id, public))
    st = match[0]
    existing = await one("clients", {"company_id": cid, "phone": norm_phone(phone)})
    over = await client_guard(cid, existing, rules, group_id) if existing and public else False
    if existing and not public and rules["noshow_enabled"]:
        over = await R.fault_count(existing["id"], rules) >= int(rules["noshow_limit"])
    client = existing or await upsert_client(cid, phone, name, email, referred_by)
    branch = await one("branches", {"id": branch_id})
    dur = int(svc["duration"]) + extra
    price = float(svc["price"]) + sum(float(a["price"]) for a in addons)
    start = m(time)
    since = (datetime.now() - timedelta(days=30)).isoformat()
    run = await db.campaign_runs.find_one({"company_id": cid, "client_ids": client["id"], "run_at": {"$gte": since}},
                                          sort=[("run_at", -1)])
    deposit = R.deposit_amount(rules, svc, dur, price, over, bool(client.get("deposit_next")))
    ps, pm = int(svc.get("pause_start") or 0), int(svc.get("pause_minutes") or 0)
    appt = {
        "id": uid(), "company_id": cid, "branch_id": branch_id, "branch_name": branch["name"],
        "stylist_id": st["stylist_id"], "stylist_name": st["stylist_name"], "client_id": client["id"],
        "client_name": client["name"], "client_phone": client["phone"], "service_id": service_id,
        "service_name": svc["name"], "addon_ids": [a["id"] for a in addons], "addon_names": [a["name"] for a in addons],
        "date": date, "time": time, "end_time": fm(start + dur), "duration": dur,
        "occ_start": start - int(svc.get("prep_minutes") or 0), "occ_end": start + dur + cleanup_of(svc, rules),
        "price": price, "deposit_required": deposit, "deposit_paid": 0,
        "deposit_status": "pending" if deposit > 0 else None,
        "deposit_due": max(min(local_now() + timedelta(hours=float(rules["deposit_hours"])),
                               datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M") - timedelta(hours=2)),
                           local_now() + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M") if deposit > 0 else None,
        "pause": [start + ps, start + ps + pm] if pm else None, "group_id": group_id, "review_token": uid() + uid(),
        "status_log": [], "status": "confirmed" if source == "staff" and deposit <= 0 else "pending", "source": source,
        "rec_type": rec_type if addons else None, "campaign_id": run["campaign_id"] if run else None,
        "reminders_sent": [], "rules": rules, "reschedule_count": 0, "created_at": now_iso()}
    await insert("appointments", appt)
    if deposit > 0 and client.get("deposit_next"):
        await db.clients.update_one({"id": client["id"]}, {"$unset": {"deposit_next": ""}})
    return appt


async def appt_rules(a, company=None):
    if a.get("rules"):
        return {**R.suggested(), **a["rules"]}
    return R.effective(company or await one("companies", {"id": a["company_id"]}), a["branch_id"])


def hours_left(a):
    return (datetime.strptime(f"{a['date']} {a['time']}", "%Y-%m-%d %H:%M") - local_now()).total_seconds() / 3600


async def reschedule(cid, appt_id, date, time, stylist_id=None, by_client=False):
    if not valid_hm(time):
        raise BookingError("Formato de hora inválido (HH:MM)")
    a = await one("appointments", {"id": appt_id, "company_id": cid})
    if not a:
        raise BookingError("Cita no encontrada")
    if by_client:
        ru = await appt_rules(a)
        if hours_left(a) < float(ru["reschedule_hours"]):
            raise BookingError(f"Solo puede reprogramar hasta {ru['reschedule_hours']:g} horas antes de su cita. Comuníquese con el salón.")
        if int(a.get("reschedule_count") or 0) >= int(ru["max_reschedules"]):
            raise BookingError(f"Esta cita ya se reprogramó el máximo de {ru['max_reschedules']} veces. Comuníquese con el salón.")
    svc = await one("services", {"id": a["service_id"]})
    extra = a["duration"] - int(svc["duration"])
    slots = await day_slots(cid, a["branch_id"], a["service_id"], date, stylist_id, exclude=appt_id, extra=extra, public=by_client)
    match = [s for s in slots if s["time"] == time]
    if not match:
        raise BookingError("Horario no disponible", await alternatives(cid, a["branch_id"], a["service_id"], date, time, stylist_id, by_client))
    start = m(time)
    upd = {"date": date, "time": time, "end_time": fm(start + a["duration"]), "stylist_id": match[0]["stylist_id"],
           "stylist_name": match[0]["stylist_name"], "occ_start": start - int(svc.get("prep_minutes") or 0),
           "occ_end": start + a["duration"] + cleanup_of(svc, await appt_rules(a)), "reminders_sent": [],
           "pause": [start + int(svc.get("pause_start") or 0), start + int(svc.get("pause_start") or 0) + int(svc["pause_minutes"])] if svc.get("pause_minutes") else None,
           "status": a["status"] if a.get("deposit_status") == "pending" else "confirmed",
           "reschedule_count": int(a.get("reschedule_count") or 0) + 1}
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


async def stock_move(cid, pid, delta, reason, ref=""):
    p = await one("products", {"id": pid, "company_id": cid})
    if not p:
        return
    await db.products.update_one({"id": pid}, {"$inc": {"stock": delta}})
    new, mn = float(p.get("stock") or 0) + delta, float(p.get("min_stock") or 0)
    if delta < 0 and new <= mn < float(p.get("stock") or 0):
        await notify_company(cid, "Existencia baja", f"{p['name']} ({new:g}/{mn:g})")
    await insert("inventory_moves", {"id": uid(), "company_id": cid, "product_id": pid, "product_name": p["name"], "qty": delta,
                                     "reason": reason, "ref": ref, "created_at": now_iso()})


def cancel_preview(a, ru, apply=True):
    hrs = hours_left(a)
    late = apply and ru["cancel_enabled"] and hrs < float(ru["cancel_hours"])
    paid = float(a.get("deposit_paid") or 0) if a.get("deposit_status") == "received" and ru["deposit_enabled"] else 0
    pct = 0 if ru["deposit_refund"] == "none" else (100 if not late else float(ru["deposit_refund_pct"]) if ru["deposit_refund"] == "partial" else 0)
    acts = {"record": "Se registra como cancelación tardía.", "notify": "Se registra y se avisa a la clienta por WhatsApp.",
            "deposit": "Se registra, se avisa a la clienta y su próxima reserva pedirá anticipo."}
    cl_acts = {"record": "Quedará registrada como cancelación tardía.", "notify": "Quedará registrada como cancelación tardía.",
               "deposit": "Quedará registrada como cancelación tardía y su próxima reserva requerirá anticipo."}
    pr = R.public_rules(ru)
    return {"late": bool(late), "hours_before": round(hrs, 1), "cancel_hours": ru["cancel_hours"], "cancel_enabled": ru["cancel_enabled"],
            "consequence": acts[ru["late_cancel_action"]] if late else "Cancelación dentro del plazo: sin penalización.",
            "client_consequence": cl_acts[ru["late_cancel_action"]] if late else "Está dentro del plazo: puede cancelar sin penalización.",
            "policy_text": pr["policy_text"], "refund_text": pr["refund_text"],
            "deposit_paid": paid, "refund": round(paid * pct / 100, 2) if paid else 0}


async def set_status(cid, appt_id, status, user=None, reason="", by_client=False, apply_policy=False):
    a = await one("appointments", {"id": appt_id, "company_id": cid})
    if not a:
        raise BookingError("Cita no encontrada")
    if a["status"] == "completed" and status != "completed" and (user or {}).get("role") not in ("company_admin", "super_admin"):
        raise BookingError("La cita ya fue atendida: solo un administrador puede corregirla")
    if a["status"] == "cancelled":
        raise BookingError("La cita ya está cancelada; cree una nueva reserva si la clienta desea volver")
    company = await one("companies", {"id": cid})
    ru = await appt_rules(a, company)
    upd = {"status": status, f"{status}_at": now_iso()}
    if status == "completed" and a["status"] != "completed" and hours_left(a) > 0:
        raise BookingError(f"La cita aún no empieza (inicia el {a['date'][8:]}/{a['date'][5:7]} a las {a['time']}). Podrá marcarla como atendida desde esa hora.")
    if status == "no_show" and a["status"] != "no_show" and hours_left(a) * 60 > -int(ru["late_tolerance_min"]):
        start = datetime.strptime(f"{a['date']} {a['time']}", "%Y-%m-%d %H:%M") + timedelta(minutes=int(ru["late_tolerance_min"]))
        raise BookingError(f"Aún no puede marcarse como falta: la tolerancia es de {ru['late_tolerance_min']} min (desde {start.strftime('%d/%m %H:%M')}).")
    if status == "cancelled":
        upd["cancel_reason"] = reason
        pv = cancel_preview(a, ru, by_client or apply_policy)
        upd["cancel_type"] = "late" if pv["late"] else "on_time" if by_client or apply_policy else "salon"
        upd["cancelled_by"] = "cliente" if by_client else "salon"
        if pv["late"]:
            upd["late_cancel"] = True
        if pv["deposit_paid"]:
            upd["deposit_refund"] = pv["refund"]
    log = {"status": status, "by": (user or {}).get("email") or ("cliente" if by_client else "sistema"), "at": now_iso(), "reason": reason}
    await db.appointments.update_one({"id": appt_id}, {"$set": upd, "$push": {"status_log": log}})
    if status == "cancelled":
        await notify_waitlist(cid, a)
        if upd.get("late_cancel"):
            await db.clients.update_one({"id": a["client_id"]}, {"$inc": {"late_cancels": 1}})
        if not by_client:
            ref = f" Le devolveremos Q{upd['deposit_refund']:.2f} de su anticipo." if upd.get("deposit_refund") else \
                " Según nuestra política, el anticipo no es reembolsable." if "deposit_refund" in upd else ""
            await wa_send(cid, a["client_phone"], f"Hola {a['client_name']}, su cita de {a['service_name']} del {a['date']} a las {a['time']} fue cancelada."
                          f"{(' Motivo: ' + reason + '.') if reason else ''}{ref}", "cancellation")
        if upd.get("late_cancel") and ru["late_cancel_action"] in ("notify", "deposit"):
            extra_msg = " Para su próxima reserva se le pedirá un anticipo." if ru["late_cancel_action"] == "deposit" else ""
            await wa_send(cid, a["client_phone"], f"Su cita fue cancelada con menos de {ru['cancel_hours']:g} horas de anticipación. "
                          f"Según nuestra política se registra como cancelación tardía.{extra_msg}", "policy")
        if upd.get("late_cancel") and ru["late_cancel_action"] == "deposit":
            await db.clients.update_one({"id": a["client_id"]}, {"$set": {"deposit_next": True}})
        if "deposit_refund" in upd:
            await notify_company(cid, "Anticipo por devolver" if upd["deposit_refund"] else "Anticipo no reembolsable",
                                 f"{a['client_name']} canceló {a['service_name']} ({a['date']} {a['time']}). Reembolso según política: Q{upd['deposit_refund']:.2f}.")
    if status == "no_show" and a["status"] != "no_show" and ru["noshow_enabled"]:
        live = R.effective(company, a["branch_id"])
        faults = await R.fault_count(a["client_id"], live)
        if faults >= int(live["noshow_limit"]):
            act = R.DEFS["noshow_action"]["options"][live["noshow_action"]]
            await notify_company(cid, "Límite de faltas superado", f"{a['client_name']} acumula {faults} falta(s) (límite {live['noshow_limit']}). Acción: {act}.")
    if status == "completed" and a["status"] != "completed":
        if "loyalty" in company.get("enabled_modules", []):
            per = float(R.effective(company, a["branch_id"])["loyalty_points_per_100"])
            await db.clients.update_one({"id": a["client_id"]}, {"$inc": {"points": int(a["price"] / 100 * per)}})
        for s in await find("services", {"id": {"$in": [a["service_id"]] + a.get("addon_ids", [])}}):
            for item in s.get("consumes") or []:
                await stock_move(cid, item["product_id"], -float(item.get("qty") or 1), f"Consumo {s['name']}", a["id"])
        await wa_send(cid, a["client_phone"], f"Gracias por visitarnos, {a['client_name']}. ¿Cómo fue su experiencia? Califíquenos aquí: "
                      f"{portal_url(company['slug'], '/resena/' + a.get('review_token', ''))}", "review")
    return {**a, **upd}


async def release_unpaid():
    now = local_now().strftime("%Y-%m-%d %H:%M")
    for a in await find("appointments", {"deposit_status": "pending", "status": "pending", "deposit_due": {"$lte": now}}):
        await set_status(a["company_id"], a["id"], "cancelled", reason="Anticipo no recibido en el plazo")
        await db.appointments.update_one({"id": a["id"]}, {"$set": {"deposit_status": "expired"}})
        await wa_send(a["company_id"], a["client_phone"], f"Su cita de {a['service_name']} del {a['date']} a las {a['time']} se liberó "
                      "porque no recibimos el anticipo a tiempo. Puede reservar de nuevo cuando guste.", "policy")
        await notify_company(a["company_id"], "Cita liberada", f"{a['client_name']} no envió el anticipo ({a['date']} {a['time']}).")


async def multi_slots(cid, branch_id, date, lines, public=False):
    svcs = [await one("services", {"id": ln["service_id"], "company_id": cid}) for ln in lines]
    if not lines or not all(svcs):
        return []
    company = await one("companies", {"id": cid})
    step = int(R.effective(company, branch_id)["slot_interval"])
    pools = [await day_slots(cid, branch_id, ln["service_id"], date, ln.get("stylist_id") or None, company=company, public=public) for ln in lines]
    out, seen = [], set()
    for first in pools[0]:
        if first["time"] in seen:
            continue
        plan, t, prev, ok = [], m(first["time"]), None, True
        for i, s in enumerate(svcs):
            cands = [first] if i == 0 else sorted([x for x in pools[i] if t <= m(x["time"]) <= t + 60], key=lambda x: (m(x["time"]), x["stylist_id"] != prev))
            if not cands:
                ok = False
                break
            pick = cands[0]
            start = m(pick["time"])
            end = start + int(s["duration"])
            plan.append({"service_id": s["id"], "service_name": s["name"], "stylist_id": pick["stylist_id"], "stylist_name": pick["stylist_name"],
                         "time": fm(start), "end_time": fm(end), "price": s["price"]})
            prev, t = pick["stylist_id"], ceil_step(end, step)
        if ok:
            seen.add(first["time"])
            out.append({"time": first["time"], "end_time": plan[-1]["end_time"], "plan": plan, "total": sum(p["price"] for p in plan)})
    return out


async def book_multi(cid, *, branch_id, date, plan, phone, **kw):
    created, gid = [], uid()
    try:
        for i, p in enumerate(plan):
            created.append(await book(cid, branch_id=branch_id, service_id=p["service_id"], date=date, time=p["time"], phone=phone,
                                      stylist_id=p["stylist_id"], group_id=gid, name=kw.get("name"), email=kw.get("email"),
                                      source=kw.get("source", "portal"), referred_by=kw.get("referred_by") if i == 0 else None,
                                      addon_ids=kw.get("addon_ids") if i == 0 else None, rec_type=kw.get("rec_type") if i == 0 else None))
    except BookingError:
        await db.appointments.delete_many({"id": {"$in": [a["id"] for a in created]}})
        raise
    return created


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
        ru = await appt_rules(a, company)
        hours = ru["reminder_hours"]
        hrs = (datetime.strptime(f"{a['date']} {a['time']}", "%Y-%m-%d %H:%M") - ln).total_seconds() / 3600
        pending = [h for h in hours if 0 < hrs <= h and h not in a.get("reminders_sent", [])]
        if not pending:
            continue
        cl = await one("clients", {"id": a["client_id"]}) or {}
        br = await one("branches", {"id": a["branch_id"]}) or {}
        text = fill(company.get("settings", {}).get("reminder_template") or DEFAULT_REMINDER, nombre=a["client_name"],
                    servicio=a["service_name"], fecha=a["date"], hora=a["time"], estilista=a["stylist_name"], sucursal=a["branch_name"],
                    direccion=br.get("address") or "", enlace=portal_url(company["slug"]), horas=min(pending),
                    horas_cancelar=f"{ru['cancel_hours']:g}", horas_reprogramar=f"{ru['reschedule_hours']:g}")
        if ru["cancel_enabled"] and not company.get("settings", {}).get("reminder_template"):
            text += f" Recuerde: puede cancelar sin costo hasta {ru['cancel_hours']:g} horas antes."
        ok = {"whatsapp": not cl.get("no_whatsapp"), "email": bool(cl.get("email"))}
        ch = next((x for x in (ru["reminder_channel"], ru["reminder_fallback"]) if ok.get(x)), None)
        if ch == "whatsapp":
            await wa_send(a["company_id"], a["client_phone"], text, "reminder")
        elif ch == "email":
            await email_send(a["company_id"], cl["email"], "Recordatorio de cita", text)
        else:
            await notify_company(a["company_id"], "Recordatorio no entregado", f"{a['client_name']} no tiene un canal de recordatorio disponible.")
        await db.appointments.update_one({"id": a["id"]}, {"$addToSet": {"reminders_sent": {"$each": pending}}})
        sent += 1
    return sent
