import os
import random
from datetime import datetime, timedelta
from core import db, one, uid, now_iso, today, hash_pw, check_pw, insert
from billing import DEFAULT_SETTINGS

MODULES = [
    ("agenda", "Agenda y citas", 0), ("crm", "CRM de clientes", 0), ("whatsapp", "Asistente WhatsApp IA", 250),
    ("portal", "Portal de reservas", 100), ("loyalty", "Fidelización", 150), ("marketing", "Marketing automatizado", 200),
    ("upsell", "Cross-selling y Upselling", 175), ("reports_adv", "Reportería avanzada", 150), ("waitlist", "Lista de espera", 75),
    ("multi_branch", "Multi-sucursal", 200),
]
DEMO_PW = "Demo2026!"


async def seed_admin():
    email, pw = os.environ["ADMIN_EMAIL"].lower(), os.environ["ADMIN_PASSWORD"]
    u = await db.users.find_one({"email": email})
    if not u:
        await db.users.insert_one({"id": uid(), "email": email, "name": "Mario Rivera", "role": "super_admin",
                                   "company_id": None, "password_hash": hash_pw(pw), "created_at": now_iso()})
    elif not check_pw(pw, u["password_hash"]):
        await db.users.update_one({"email": email}, {"$set": {"password_hash": hash_pw(pw)}})


async def seed_all():
    await db.users.create_index("email", unique=True)
    await db.companies.create_index("slug", unique=True)
    await db.clients.create_index([("company_id", 1), ("phone", 1)], unique=True)
    await db.appointments.create_index([("company_id", 1), ("date", 1)])
    await db.wa_messages.create_index([("company_id", 1), ("phone", 1), ("created_at", 1)])
    await seed_admin()
    if await db.plans.count_documents({}):
        return
    for k, n, p in MODULES:
        await insert("modules", {"id": uid(), "key": k, "name": n, "price_monthly": p, "created_at": now_iso()})
    await db.platform_settings.update_one({"id": "global"}, {"$set": {
        "id": "global", "currency": "GTQ", "tax_rate": 12, "annual_discount": 15, "trial_days": 14, "grace_days": 7,
        "retry_days": [1, 3, 5], "extra_branch_price": 150, "extra_stylist_price": 50, "wa_pack_price": 100, "wa_pack_size": 500,
        "wa_cost_per_message": 0.05, "wa_excess_price": 0.12}}, upsert=True)
    plans = [
        ("Básico", 350, ["agenda", "crm", "portal"], 1, 3, 500),
        ("Profesional", 750, ["agenda", "crm", "portal", "whatsapp", "waitlist", "loyalty"], 2, 8, 2000),
        ("Premium", 1400, [k for k, _, _ in MODULES], 5, 25, 6000),
    ]
    pids = {}
    for n, p, mods, mb, ms, wa in plans:
        pids[n] = uid()
        await insert("plans", {"id": pids[n], "name": n, "price_monthly": p, "included_modules": mods, "max_branches": mb,
                               "max_stylists": ms, "wa_messages": wa, "active": True, "created_at": now_iso()})
    await insert("platform_coupons", {"id": uid(), "code": "PILOTO50", "percent": 50, "description": "Clientes piloto", "created_at": now_iso()})
    await seed_demo(pids["Premium"])


async def seed_demo(plan_id):
    td = datetime.strptime(today(), "%Y-%m-%d")
    cid = uid()
    settings = {**DEFAULT_SETTINGS, "holidays": [f"{td.year}-12-25", f"{td.year}-09-15"],
                "loyalty": {**DEFAULT_SETTINGS["loyalty"], "memberships": [{"name": "Oro", "discount": 10, "price": 250}]}}
    await insert("companies", {
        "id": cid, "name": "Salón Bella Vida (Demo)", "slug": "bellavida", "nit": "1234567-8", "contact_name": "Ana López",
        "contact_email": "admin@bellavida.com", "phone": "+50222220000", "whatsapp_number": "+50255550001", "plan_id": plan_id,
        "billing_cycle": "monthly", "currency": "GTQ", "enabled_modules": [k for k, _, _ in MODULES], "status": "active",
        "trial_ends": None, "next_billing_date": (td + timedelta(days=12)).strftime("%Y-%m-%d"), "converted": True,
        "card": {"token": "tok_sim_demo", "last4": "4242", "brand": "Visa", "exp": "12/29"}, "coupon_pct": 0,
        "settings": settings, "wa_packs": 0, "terms_accepted_at": now_iso(), "created_at": now_iso()})
    hours = {str(d): ["09:00", "19:00"] for d in range(6)}
    b1, b2 = uid(), uid()
    await insert("branches", {"id": b1, "company_id": cid, "name": "Zona 10", "address": "Av. La Reforma 12-01, Zona 10", "phone": "+50222220001", "hours": hours, "capacity": 4, "created_at": now_iso()})
    await insert("branches", {"id": b2, "company_id": cid, "name": "Cayalá", "address": "Paseo Cayalá, Local 23", "phone": "+50222220002", "hours": {**hours, "6": ["10:00", "16:00"]}, "capacity": 3, "created_at": now_iso()})
    sty = [("Carla Méndez", b1, "Colorimetría, Balayage"), ("Diego Ruiz", b1, "Corte, Barbería"),
           ("Lucía Pérez", b1, "Manicure, Pedicure"), ("Sofía Castillo", b2, "Keratina, Tratamientos, Corte")]
    sids = []
    for n, b, sp in sty:
        sids.append(uid())
        await insert("stylists", {"id": sids[-1], "company_id": cid, "name": n, "branch_id": b, "specialties": sp, "active": True, "hours": {}, "created_at": now_iso()})
    svcs = [("Corte de cabello", "Cabello", 45, 150, 0, 5, 30, [sids[1], sids[3]]), ("Tratamiento capilar", "Cabello", 30, 180, 0, 5, 0, []),
            ("Tinte", "Color", 90, 450, 10, 10, 45, [sids[0], sids[3]]), ("Mascarilla nutritiva", "Cabello", 20, 120, 0, 0, 0, []),
            ("Balayage", "Color", 180, 1200, 15, 15, 90, [sids[0]]), ("Keratina", "Tratamientos", 150, 900, 10, 15, 120, [sids[3]]),
            ("Manicure Básico", "Uñas", 40, 100, 0, 10, 21, [sids[2]]), ("Manicure Spa Premium", "Uñas", 60, 200, 0, 10, 21, [sids[2]]),
            ("Pedicure", "Uñas", 50, 150, 0, 10, 30, [sids[2]]), ("Spa de pies", "Uñas", 30, 140, 0, 5, 0, [sids[2]]),
            ("Barbería clásica", "Barbería", 30, 120, 0, 5, 21, [sids[1]])]
    svc = {}
    for n, cat, d, p, prep, cl, rb, st in svcs:
        svc[n] = {"id": uid(), "company_id": cid, "name": n, "category": cat, "description": f"{n} profesional", "duration": d, "price": p,
                  "cost": round(p * 0.3, 2), "deposit": 0, "prep_minutes": prep, "cleanup_minutes": cl, "rebook_days": rb,
                  "stylist_ids": st, "active": True, "created_at": now_iso()}
        await insert("services", svc[n])
    rules = [("cross", "Corte de cabello", "Tratamiento capilar", "Complementa tu corte con un tratamiento capilar"),
             ("cross", "Tinte", "Mascarilla nutritiva", "Protege tu color con una mascarilla nutritiva"),
             ("cross", "Manicure Básico", "Pedicure", "¿Agregamos pedicure?"), ("cross", "Pedicure", "Spa de pies", "Relájate con un spa de pies"),
             ("up", "Manicure Básico", "Manicure Spa Premium", "Mejora a Manicure Spa Premium")]
    for t, a, b, msg in rules:
        await insert("upsell_rules", {"id": uid(), "company_id": cid, "type": t, "trigger_service_id": svc[a]["id"],
                                      "suggested_service_id": svc[b]["id"], "message": msg, "active": True, "created_at": now_iso()})
    camps = [("Feliz cumpleaños", "birthday", "¡Feliz cumpleaños {nombre}! En {salon} te regalamos 15% en tu próxima cita."),
             ("Te extrañamos", "inactive", "Hola {nombre}, hace tiempo no te vemos en {salon}. Agenda esta semana y recibe 10% de descuento."),
             ("Retoque de color", "retouch", "Hola {nombre}, ya es momento de tu retoque. ¡Agenda con nosotros!")]
    for n, t, msg in camps:
        await insert("campaigns", {"id": uid(), "company_id": cid, "name": n, "type": t, "channel": "whatsapp", "days": 60, "message": msg, "active": True, "sent_total": 0, "created_at": now_iso()})
    await insert("loyalty_coupons", {"id": uid(), "company_id": cid, "code": "BIENVENIDA10", "percent": 10, "description": "Primera visita", "created_at": now_iso()})
    users = [("admin@bellavida.com", "Ana López", "company_admin", None, None), ("gerente@bellavida.com", "Luis Gómez", "branch_manager", b1, None),
             ("recepcion@bellavida.com", "María Torres", "receptionist", None, None), ("estilista@bellavida.com", "Carla Méndez", "stylist", b1, sids[0])]
    for e, n, rl, b, s in users:
        await db.users.insert_one({"id": uid(), "email": e, "name": n, "role": rl, "company_id": cid, "branch_id": b, "stylist_id": s,
                                   "active": True, "password_hash": hash_pw(DEMO_PW), "created_at": now_iso()})
    clients = [("Gabriela Morales", "+50250001111", "1990-%s" % (td + timedelta(days=2)).strftime("%m-%d"), "F"), ("Andrea Díaz", "+50250002222", "1985-03-14", "F"),
               ("José Herrera", "+50250003333", "1992-07-21", "M"), ("Valeria Cruz", "+50250004444", "1998-11-02", "F"),
               ("Fernanda Ramírez", "+50250005555", "1988-01-30", "F"), ("Carlos Méndez", "+50250006666", "1979-05-09", "M")]
    cl = []
    for n, p, bd, g in clients:
        cl.append({"id": uid(), "company_id": cid, "name": n, "phone": p, "email": n.split()[0].lower() + "@correo.com", "birthdate": bd,
                   "gender": g, "points": 0, "membership": "", "notes": {}, "referred_by": "", "created_at": (td - timedelta(days=random.randint(1, 200))).isoformat()})
        await insert("clients", cl[-1])
    random.seed(7)
    plan = [(svc["Tinte"], sids[0], b1), (svc["Corte de cabello"], sids[1], b1), (svc["Manicure Básico"], sids[2], b1),
            (svc["Keratina"], sids[3], b2), (svc["Pedicure"], sids[2], b1), (svc["Corte de cabello"], sids[3], b2), (svc["Balayage"], sids[0], b1)]
    names = {s: n for s, (n, _, _) in zip(sids, sty)}
    bnames = {b1: "Zona 10", b2: "Cayalá"}
    for i in range(170):
        s, st, b = random.choice(plan)
        c = random.choice(cl)
        delta = random.randint(-75, 12)
        d = td + timedelta(days=delta)
        if d.weekday() == 6:
            continue
        h = random.choice([9, 10, 11, 12, 14, 15, 16])
        start = h * 60
        status = "completed" if delta < 0 else "confirmed" if delta > 0 else "pending"
        if delta < 0 and random.random() < 0.12:
            status = random.choice(["cancelled", "no_show"])
        ds = d.strftime("%Y-%m-%d")
        if await db.appointments.find_one({"stylist_id": st, "date": ds, "occ_start": {"$lt": start + s["duration"] + 30}, "occ_end": {"$gt": start - 30}}):
            continue
        addon = svc["Pedicure"] if s["name"] == "Manicure Básico" and random.random() < 0.4 else None
        dur = s["duration"] + (addon["duration"] if addon else 0)
        await insert("appointments", {
            "id": uid(), "company_id": cid, "branch_id": b, "branch_name": bnames[b], "stylist_id": st, "stylist_name": names[st],
            "client_id": c["id"], "client_name": c["name"], "client_phone": c["phone"], "service_id": s["id"], "service_name": s["name"],
            "addon_ids": [addon["id"]] if addon else [], "addon_names": [addon["name"]] if addon else [], "date": ds,
            "time": f"{h:02d}:00", "end_time": f"{(start + dur) // 60:02d}:{(start + dur) % 60:02d}", "duration": dur,
            "occ_start": start - s["prep_minutes"], "occ_end": start + dur + s["cleanup_minutes"],
            "price": s["price"] + (addon["price"] if addon else 0), "deposit_required": 0, "deposit_paid": 0, "status": status,
            "source": random.choice(["whatsapp", "portal", "staff"]), "rec_type": "cross" if addon else None, "campaign_id": None,
            "reminders_sent": [], "created_at": (d - timedelta(days=3)).isoformat()})
        if status == "completed":
            await db.clients.update_one({"id": c["id"]}, {"$inc": {"points": int(s["price"] / 10)}})
    for k in ("cross", "up"):
        for _ in range(12 if k == "cross" else 5):
            await db.rec_offers.insert_one({"company_id": cid, "type": k, "created_at": now_iso()})
    for i, (amt, days) in enumerate([(1400, 48), (1400, 18)]):
        d = (td - timedelta(days=days)).strftime("%Y-%m-%d")
        iid = uid()
        await insert("invoices", {"id": iid, "company_id": cid, "company_name": "Salón Bella Vida (Demo)", "nit": "1234567-8",
                                  "number": f"FAC-{i + 1:06d}", "date": d, "items": [{"desc": "Plan Premium", "amount": amt, "kind": "plan"}],
                                  "subtotal": amt, "tax": amt * 0.12, "total": amt * 1.12, "currency": "GTQ", "status": "paid",
                                  "kind": "subscription", "plan_name": "Premium", "fel": {"uuid": uid().upper(), "serie": "SIM", "certificador": "SIMULADO - INFILE/Digifact pendiente"},
                                  "created_at": now_iso()})
        await insert("payments", {"id": uid(), "company_id": cid, "company_name": "Salón Bella Vida (Demo)", "invoice_id": iid,
                                  "invoice_number": f"FAC-{i + 1:06d}", "amount": amt * 1.12, "currency": "GTQ", "method": "card",
                                  "status": "approved", "reference": "SIM-demo", "date": d, "created_at": now_iso()})
