import io
import uuid
from datetime import datetime, timedelta
from core import db, find, one, uid, now_iso, today, insert, email_send

DEFAULT_SETTINGS = {
    "holidays": [], "deposit_rules": [{"min_minutes": 120, "percent": 30}], "reminder_hours": [48, 24, 2],
    "loyalty": {"points_per_100": 10, "redeem_value": 0.1, "referral_points": 50, "memberships": []},
    "portal": {"tagline": "Reserva tu cita en segundos", "hero": ""},
}


async def psettings():
    return await one("platform_settings", {"id": "global"}) or {}


def advance(date_str, cycle):
    return (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=365 if cycle == "annual" else 30)).strftime("%Y-%m-%d")


async def breakdown(company):
    s = await psettings()
    plan = await one("plans", {"id": company.get("plan_id")}) or {}
    mods = {x["key"]: x for x in await find("modules", {})}
    items = [{"desc": f"Plan {plan.get('name', '-')}", "amount": float(plan.get("price_monthly", 0)), "kind": "plan"}]
    for k in company.get("enabled_modules", []):
        if k not in plan.get("included_modules", []) and k in mods:
            items.append({"desc": f"Módulo {mods[k]['name']}", "amount": float(mods[k]["price_monthly"]), "kind": "module", "key": k})
    nb = await db.branches.count_documents({"company_id": company["id"]})
    ns = await db.stylists.count_documents({"company_id": company["id"]})
    eb, es = max(0, nb - int(plan.get("max_branches", 1))), max(0, ns - int(plan.get("max_stylists", 3)))
    if eb:
        items.append({"desc": f"{eb} sucursal(es) adicional(es)", "amount": eb * float(s.get("extra_branch_price", 0)), "kind": "extra"})
    if es:
        items.append({"desc": f"{es} estilista(s) adicional(es)", "amount": es * float(s.get("extra_stylist_price", 0)), "kind": "extra"})
    wp = int(company.get("wa_packs") or 0)
    if wp:
        items.append({"desc": f"{wp} paquete(s) de mensajes WhatsApp", "amount": wp * float(s.get("wa_pack_price", 0)), "kind": "extra"})
    return items


async def cycle_items(company):
    s = await psettings()
    items = await breakdown(company)
    if company.get("billing_cycle") == "annual":
        f = 12 * (1 - float(s.get("annual_discount", 0)) / 100)
        items = [{**i, "amount": round(i["amount"] * f, 2)} for i in items]
    pct = float(company.get("coupon_pct") or 0)
    if pct:
        items.append({"desc": f"Descuento cupón {company.get('coupon_code', '')} ({pct}%)",
                      "amount": -round(sum(i["amount"] for i in items) * pct / 100, 2), "kind": "discount"})
    return items


async def monthly_value(company):
    items = await cycle_items(company)
    total = sum(i["amount"] for i in items)
    return round(total / 12 if company.get("billing_cycle") == "annual" else total, 2)


async def create_invoice(company, items, kind="subscription"):
    s = await psettings()
    sub = round(sum(i["amount"] for i in items), 2)
    tax = round(sub * float(s.get("tax_rate", 12)) / 100, 2)
    n = await db.invoices.count_documents({}) + 1
    plan = await one("plans", {"id": company.get("plan_id")}) or {}
    inv = {"id": uid(), "company_id": company["id"], "company_name": company["name"], "nit": company.get("nit") or "CF",
           "number": f"FAC-{n:06d}", "date": today(), "items": items, "subtotal": sub, "tax": tax, "total": round(sub + tax, 2),
           "currency": company.get("currency", "GTQ"), "status": "pending", "kind": kind, "plan_name": plan.get("name", ""),
           "fel": {"uuid": str(uuid.uuid4()).upper(), "serie": "SIM", "certificador": "SIMULADO - INFILE/Digifact pendiente"},
           "created_at": now_iso()}
    return await insert("invoices", inv)


async def notify(company, title, text):
    await insert("notifications", {"id": uid(), "company_id": company["id"], "title": title, "text": text,
                                   "channels": ["email", "whatsapp"], "created_at": now_iso()})
    await email_send(company["id"], company.get("contact_email", ""), title, text)


async def mark_paid(company, inv):
    await db.invoices.update_one({"id": inv["id"]}, {"$set": {"status": "paid", "paid_at": now_iso()}})
    if inv["kind"] == "subscription":
        await db.companies.update_one({"id": company["id"]}, {"$set": {
            "next_billing_date": advance(inv["date"], company.get("billing_cycle")), "converted": True}})
    await email_send(company["id"], company.get("contact_email", ""), f"Factura {inv['number']}", "Adjuntamos su factura electrónica.")
    open_ = await db.invoices.count_documents({"company_id": company["id"], "status": {"$in": ["pending", "failed"]}})
    if open_ == 0 and company["status"] != "cancelled":
        await db.companies.update_one({"id": company["id"]}, {"$set": {"status": "active", "past_due_since": None}})


async def charge(company, inv):
    card = company.get("card")
    ok = bool(card) and card.get("last4") != "0002"
    await insert("payments", {"id": uid(), "company_id": company["id"], "company_name": company["name"], "invoice_id": inv["id"],
                              "invoice_number": inv["number"], "amount": inv["total"], "currency": inv["currency"], "method": "card",
                              "status": "approved" if ok else "rejected", "reference": f"SIM-{uid()}", "date": today(),
                              "created_at": now_iso()})
    if ok:
        await mark_paid(company, inv)
        await notify(company, "Cobro exitoso", f"Se cobró {inv['currency']} {inv['total']:.2f} de la factura {inv['number']}.")
    else:
        await db.invoices.update_one({"id": inv["id"]}, {"$set": {"status": "failed"}})
        if company["status"] not in ("past_due", "suspended_partial", "suspended"):
            await db.companies.update_one({"id": company["id"]}, {"$set": {"status": "past_due", "past_due_since": today()}})
        await notify(company, "Cobro rechazado", f"No pudimos cobrar la factura {inv['number']}. Actualice su tarjeta para evitar la suspensión.")
    return ok


async def prorate_module(company, key):
    if company["status"] == "trial":
        return None
    s = await psettings()
    mod = await one("modules", {"key": key})
    plan = await one("plans", {"id": company.get("plan_id")}) or {}
    if not mod or key in plan.get("included_modules", []):
        return None
    annual = company.get("billing_cycle") == "annual"
    period = 365 if annual else 30
    days_left = (datetime.strptime(company.get("next_billing_date") or today(), "%Y-%m-%d") - datetime.strptime(today(), "%Y-%m-%d")).days
    price = float(mod["price_monthly"]) * (12 * (1 - float(s.get("annual_discount", 0)) / 100) if annual else 1)
    amount = round(price * max(days_left, 0) / period, 2)
    if amount <= 0:
        return None
    inv = await create_invoice(company, [{"desc": f"Prorrateo módulo {mod['name']} ({days_left} días)", "amount": amount,
                                          "kind": "module", "key": key}], "proration")
    if company.get("card"):
        await charge(company, inv)
    return inv


async def run_billing():
    s = await psettings()
    td = today()
    res = {"charged": 0, "failed": 0, "status_changes": 0}
    for c in await find("companies", {"status": {"$ne": "cancelled"}}):
        due_trial = c["status"] == "trial" and (c.get("trial_ends") or "9999") <= td
        due_active = c["status"] == "active" and (c.get("next_billing_date") or "9999") <= td
        if due_trial or due_active:
            inv = await create_invoice(c, await cycle_items(c))
            ok = await charge(c, inv)
            res["charged" if ok else "failed"] += 1
            continue
        if c["status"] not in ("past_due", "suspended_partial", "suspended") or not c.get("past_due_since"):
            continue
        days = (datetime.strptime(td, "%Y-%m-%d") - datetime.strptime(c["past_due_since"], "%Y-%m-%d")).days
        if days in s.get("retry_days", [1, 3, 5]):
            for inv in await find("invoices", {"company_id": c["id"], "status": "failed"}):
                c = await one("companies", {"id": c["id"]})
                await charge(c, inv)
        c = await one("companies", {"id": c["id"]})
        if c["status"] == "active":
            continue
        grace = int(s.get("grace_days", 7))
        new = "suspended" if days >= grace + 7 else "suspended_partial" if days >= grace else "past_due"
        if new != c["status"]:
            await db.companies.update_one({"id": c["id"]}, {"$set": {"status": new}})
            await notify(c, "Cambio de estado de cuenta", f"Su cuenta pasó a estado: {new}.")
            res["status_changes"] += 1
        elif new == "past_due" and days in s.get("retry_days", [1, 3, 5]):
            await notify(c, "Aviso de suspensión", f"Su cuenta será suspendida en {grace - days} días si no se registra el pago.")
    return res


async def statement(company):
    s = await psettings()
    plan = await one("plans", {"id": company.get("plan_id")}) or {}
    items = await breakdown(company)
    invoices = await find("invoices", {"company_id": company["id"]}, [("created_at", -1)])
    payments = await find("payments", {"company_id": company["id"]}, [("created_at", -1)])
    charged = round(sum(i["total"] for i in invoices if i["status"] != "void"), 2)
    paid = round(sum(p["amount"] for p in payments if p["status"] == "approved"), 2)
    month = today()[:8] + "01"
    used = await db.wa_messages.count_documents({"company_id": company["id"], "created_at": {"$gte": month}})
    included = int(plan.get("wa_messages", 0)) + int(company.get("wa_packs") or 0) * int(s.get("wa_pack_size", 500))
    excess = max(0, used - included)
    cyc = await cycle_items(company)
    return {"company": {k: company.get(k) for k in ("id", "name", "nit", "status", "billing_cycle", "currency", "next_billing_date",
                                                    "trial_ends", "card", "enabled_modules", "plan_id", "coupon_code", "slug")},
            "plan": plan, "items": items, "monthly_total": round(sum(i["amount"] for i in items), 2),
            "cycle_total": round(sum(i["amount"] for i in cyc), 2), "invoices": invoices, "payments": payments,
            "charged": charged, "paid": paid, "balance": round(charged - paid, 2),
            "whatsapp": {"used": used, "included": included, "excess": excess,
                         "excess_cost": round(excess * float(s.get("wa_excess_price", 0.1)), 2)}}


def invoice_pdf(inv):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    p = canvas.Canvas(buf, pagesize=letter)
    y = 740
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, y, f"Factura {inv['number']}")
    p.setFont("Helvetica", 10)
    for line in [f"Fecha: {inv['date']}", f"Cliente: {inv['company_name']}", f"NIT: {inv['nit']}",
                 f"FEL UUID: {inv['fel']['uuid']}", f"Certificador: {inv['fel']['certificador']}", f"Estado: {inv['status']}"]:
        y -= 16
        p.drawString(50, y, line)
    y -= 30
    p.setFont("Helvetica-Bold", 10)
    p.drawString(50, y, "Descripción")
    p.drawRightString(550, y, f"Monto ({inv['currency']})")
    p.setFont("Helvetica", 10)
    for it in inv["items"]:
        y -= 16
        p.drawString(50, y, it["desc"][:80])
        p.drawRightString(550, y, f"{it['amount']:.2f}")
    for label, val in [("Subtotal", inv["subtotal"]), ("IVA", inv["tax"]), ("Total", inv["total"])]:
        y -= 18
        p.drawString(380, y, label)
        p.drawRightString(550, y, f"{val:.2f}")
    p.showPage()
    p.save()
    return buf.getvalue()
