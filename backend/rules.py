from datetime import timedelta
from fastapi import APIRouter, Depends, Body, HTTPException
from core import db, one, find, audit, guard, local_now, fill, ALL_STAFF

r = APIRouter(prefix="/api")
ADMIN = ("company_admin",)

GROUPS = {"A": "Cancelación y reprogramación", "B": "Anticipo manual", "C": "Faltas (no asistió)",
          "D": "Reservas y horarios", "E": "Comisiones", "F": "Puntos, fidelización y recordatorios"}

POLICY_TEXT = ("Puede cancelar sin costo hasta {horas_cancelar} horas antes de su cita y reprogramar hasta {horas_reprogramar} horas antes "
               "(máximo {max_reprogramaciones} veces por cita). Las cancelaciones fuera de plazo quedan registradas.")

# key, group, label, description, type, suggested, extra
SCHEMA = [
    ("cancel_enabled", "A", "Política de cancelación", "Activa el control de cancelaciones tardías y muestra la política en el portal.", "bool", True, {}),
    ("cancel_hours", "A", "Horas mínimas para cancelar sin costo", "Si la clienta cancela con menos horas, se considera cancelación tardía.", "num", 24, {"max": 720}),
    ("reschedule_hours", "A", "Horas mínimas para reprogramar", "Con menos horas, la clienta ya no puede reprogramar desde el portal o WhatsApp.", "num", 12, {"max": 720}),
    ("max_reschedules", "A", "Máximo de reprogramaciones por cita", "Cuántas veces la clienta puede mover una misma cita.", "int", 2, {"max": 50}),
    ("late_cancel_action", "A", "Qué pasa con una cancelación tardía", "Acción automática cuando la clienta cancela fuera de plazo.", "enum", "notify",
     {"options": {"record": "Solo registrar", "notify": "Registrar y avisar a la clienta", "deposit": "Registrar, avisar y exigir anticipo la próxima vez"}}),
    ("cancel_policy_text", "A", "Texto de la política", "Lo que ve la clienta en el portal y en la confirmación. Use {horas_cancelar}, {horas_reprogramar}, {max_reprogramaciones}.", "longtext", POLICY_TEXT, {}),
    ("deposit_enabled", "B", "Anticipo", "Exige un anticipo por transferencia para ciertas reservas.", "bool", True, {}),
    ("deposit_when", "B", "Cuándo se exige", "Una o varias condiciones; basta con que se cumpla una.", "multi", ["duration"],
     {"options": {"duration": "Por duración del servicio", "price": "Por precio mínimo", "services": "Por servicio específico", "no_shows": "A clientas con faltas"}}),
    ("deposit_min_minutes", "B", "Duración mínima (min)", "Servicios con esta duración o más requieren anticipo.", "int", 120, {"max": 1440}),
    ("deposit_min_price", "B", "Precio mínimo", "Servicios con este precio o más requieren anticipo.", "num", 500, {}),
    ("deposit_service_ids", "B", "Servicios que siempre piden anticipo", "Seleccione los servicios específicos.", "services", [], {}),
    ("deposit_type", "B", "Tipo de monto", "Porcentaje del precio o monto fijo. El monto fijo de un servicio (en Servicios) tiene prioridad.", "enum", "percent",
     {"options": {"percent": "Porcentaje", "fixed": "Monto fijo"}}),
    ("deposit_percent", "B", "Porcentaje de anticipo", "Porcentaje del precio total del servicio.", "num", 30, {"max": 100, "pct": True}),
    ("deposit_fixed", "B", "Monto fijo de anticipo", "Se usa cuando el tipo es monto fijo.", "num", 100, {}),
    ("deposit_hours", "B", "Horas para pagar el anticipo", "Si no llega en este plazo, la cita se libera sola.", "num", 12, {"min": 1, "max": 720}),
    ("bank_name", "B", "Banco", "Datos que verá la clienta para transferir.", "text", "", {}),
    ("bank_account", "B", "Número de cuenta", "", "text", "", {}),
    ("bank_holder", "B", "Titular de la cuenta", "", "text", "", {}),
    ("bank_message", "B", "Mensaje para el comprobante", "Ej.: escriba su nombre y fecha de cita en la descripción.", "text", "", {}),
    ("deposit_whatsapp", "B", "WhatsApp para el comprobante", "Número donde la clienta envía la foto del comprobante.", "text", "", {}),
    ("deposit_refund", "B", "Reembolso del anticipo", "Qué se devuelve si la clienta cancela.", "enum", "until_limit",
     {"options": {"until_limit": "Reembolsable hasta el límite de cancelación", "partial": "Parcial si cancela tarde", "none": "No reembolsable"}}),
    ("deposit_refund_pct", "B", "Porcentaje reembolsable si cancela tarde", "Solo aplica al reembolso parcial.", "num", 50, {"max": 100, "pct": True}),
    ("noshow_enabled", "C", "Control de faltas", "Cuenta las faltas de cada clienta y actúa al superar el límite.", "bool", True, {}),
    ("noshow_limit", "C", "Faltas permitidas antes de actuar", "Al llegar a este número de faltas se aplica la acción.", "int", 3, {"min": 1, "max": 50}),
    ("noshow_action", "C", "Acción al superar el límite", "Qué hace el sistema con la clienta.", "enum", "alert_deposit",
     {"options": {"alert": "Alertar al dueño", "alert_deposit": "Alertar y exigir anticipo", "block": "Alertar y bloquear la reserva en línea"}}),
    ("noshow_months", "C", "Periodo en que cuentan las faltas (meses)", "0 = siempre.", "int", 6, {"max": 120}),
    ("late_tolerance_min", "C", "Minutos de tolerancia", "No se puede marcar falta hasta que pasen estos minutos desde la hora de la cita.", "int", 15, {"max": 240}),
    ("min_advance_hours", "D", "Anticipación mínima para reservar en línea (h)", "Horarios más cercanos no se ofrecen en portal ni WhatsApp.", "num", 2, {"max": 720}),
    ("max_advance_days", "D", "Anticipación máxima (días)", "Hasta cuántos días adelante se puede reservar en línea.", "int", 60, {"min": 1, "max": 730}),
    ("slot_interval", "D", "Intervalo de horarios", "Cada cuántos minutos se ofrecen horarios.", "enum", 30, {"options": {15: "15 min", 30: "30 min", 60: "60 min"}}),
    ("default_cleanup_min", "D", "Limpieza entre citas (min)", "Se usa en servicios que no tienen limpieza propia.", "int", 10, {"max": 240}),
    ("max_active_per_client", "D", "Máximo de citas activas por clienta", "Visitas futuras pendientes o confirmadas en línea.", "int", 3, {"min": 1, "max": 50}),
    ("commission_model", "E", "Modelo de comisión", "Cómo se paga a las estilistas.", "enum", "percent",
     {"options": {"percent": "Porcentaje", "fixed": "Monto fijo por servicio", "salary_plus": "Sueldo fijo más comisión"}}),
    ("commission_percent", "E", "Porcentaje general", "Las excepciones por estilista y por servicio se definen en Estilistas y Servicios.", "num", 30, {"max": 100, "pct": True}),
    ("commission_fixed", "E", "Monto fijo general por servicio", "Para el modelo de monto fijo, salvo que la estilista tenga el suyo.", "num", 0, {}),
    ("tips_in_commission", "E", "Las propinas entran en la comisión", "Si se activa, la comisión también se calcula sobre la propina.", "bool", False, {}),
    ("pay_period", "E", "Periodo de pago", "Periodo que propone la pantalla de comisiones.", "enum", "biweekly",
     {"options": {"weekly": "Semanal", "biweekly": "Quincenal", "monthly": "Mensual"}}),
    ("loyalty_points_per_100", "F", "Puntos por cada Q100 gastados", "Si el módulo de fidelización está activo.", "num", 10, {}),
    ("loyalty_redeem_value", "F", "Valor de canje por punto (Q)", "Cuánto vale cada punto al canjearlo.", "num", 0.1, {}),
    ("reminder_hours", "F", "Horas de los recordatorios", "Horas antes de la cita, separadas por coma.", "hours", [24, 2], {}),
    ("reminder_channel", "F", "Canal preferido de recordatorio", "", "enum", "whatsapp", {"options": {"whatsapp": "WhatsApp", "email": "Correo"}}),
    ("reminder_fallback", "F", "Alternativa si falla", "Si la clienta no tiene el canal preferido.", "enum", "email",
     {"options": {"email": "Correo", "whatsapp": "WhatsApp", "none": "Ninguna (avisar al salón)"}}),
]
DEFS = {k: {"key": k, "group": g, "label": lab, "desc": d, "type": t, "suggested": s, **x} for k, g, lab, d, t, s, x in SCHEMA}
SUGGESTED_BY_COUNTRY = {"GT": {}}


def suggested(country=None):
    return {**{k: d["suggested"] for k, d in DEFS.items()}, **SUGGESTED_BY_COUNTRY.get(country or "GT", {})}


def effective(company, branch_id=None):
    out = suggested(company.get("country"))
    for layer in (company.get("rules") or {}, (company.get("branch_rules") or {}).get(branch_id or "", {})):
        out.update({k: v for k, v in layer.items() if k in DEFS and v is not None})
    return out


def validate(key, v):
    d = DEFS.get(key)
    if not d:
        raise HTTPException(400, f"Regla desconocida: {key}")
    lab, t = d["label"], d["type"]
    if t == "bool":
        if not isinstance(v, bool):
            raise HTTPException(400, f"«{lab}»: debe ser sí o no")
        return v
    if t in ("num", "int"):
        if v is None or (isinstance(v, str) and not v.strip()):
            raise HTTPException(400, f"«{lab}»: no puede quedar vacío")
        try:
            n = float(v)
        except (TypeError, ValueError):
            raise HTTPException(400, f"«{lab}»: debe ser un número")
        if n < 0:
            raise HTTPException(400, f"«{lab}»: no puede ser negativo")
        if t == "int" and n != int(n):
            raise HTTPException(400, f"«{lab}»: debe ser un número entero")
        if n < d.get("min", 0):
            raise HTTPException(400, f"«{lab}»: el mínimo es {d['min']}")
        if "max" in d and n > d["max"]:
            raise HTTPException(400, f"«{lab}»: " + ("un porcentaje no puede ser mayor a 100" if d.get("pct") else f"el máximo es {d['max']}"))
        return int(n) if n == int(n) else n
    if t == "enum":
        opts = d["options"]
        if v not in opts and str(v) not in {str(o) for o in opts}:
            raise HTTPException(400, f"«{lab}»: opción no válida")
        return next(o for o in opts if str(o) == str(v))
    if t == "multi":
        if not isinstance(v, list) or any(x not in d["options"] for x in v):
            raise HTTPException(400, f"«{lab}»: opción no válida")
        return v
    if t == "services":
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise HTTPException(400, f"«{lab}»: lista de servicios inválida")
        return v
    if t == "hours":
        try:
            hs = sorted({float(x) for x in v}, reverse=True)
        except (TypeError, ValueError):
            raise HTTPException(400, f"«{lab}»: escriba horas separadas por coma")
        if not hs or any(h <= 0 or h > 168 for h in hs):
            raise HTTPException(400, f"«{lab}»: cada hora debe estar entre 1 y 168")
        return [int(h) if h == int(h) else h for h in hs]
    if not isinstance(v, str) or len(v) > (2000 if t == "longtext" else 200):
        raise HTTPException(400, f"«{lab}»: texto demasiado largo")
    if t == "longtext" and not v.strip():
        raise HTTPException(400, f"«{lab}»: no puede quedar vacío")
    return v.strip()


def show(key, v):
    d = DEFS[key]
    if v is None:
        return "(regla general)"
    if d["type"] == "bool":
        return "Sí" if v else "No"
    if d["type"] == "enum":
        return next((lab for o, lab in d["options"].items() if str(o) == str(v)), str(v))
    if d["type"] == "multi":
        return ", ".join(d["options"].get(x, x) for x in v) or "-"
    if isinstance(v, (int, float)):
        return f"{v:g}"
    if isinstance(v, list):
        return ", ".join(f"{x:g}" if isinstance(x, (int, float)) else str(x) for x in v) or "-"
    return str(v)[:120]


async def save_rules(c, values, branch_id=None):
    co = c["company"]
    if branch_id and not await one("branches", {"id": branch_id, "company_id": c["cid"]}):
        raise HTTPException(404, "Sucursal no encontrada")
    cur = dict((co.get("branch_rules") or {}).get(branch_id, {}) if branch_id else co.get("rules") or {})
    before = effective(co, branch_id)
    clean = {k: (None if v is None else validate(k, v)) for k, v in values.items()}
    for k, v in clean.items():
        if v is None:
            cur.pop(k, None)
        else:
            cur[k] = v
    field = f"branch_rules.{branch_id}" if branch_id else "rules"
    await db.companies.update_one({"id": c["cid"]}, {"$set": {field: cur, "rules_reviewed": True}})
    co = await one("companies", {"id": c["cid"]})
    after = effective(co, branch_id)
    scope = f"Sucursal {(await one('branches', {'id': branch_id}))['name']}" if branch_id else "General"
    for k in clean:
        if show(k, before.get(k)) != show(k, after.get(k)) or (DEFS[k]["type"] == "longtext" and before.get(k) != after.get(k)):
            await audit(c["user"], c["cid"], "rule_change", "reglas", f"[{scope}] {DEFS[k]['label']}: {show(k, before.get(k))} → {show(k, after.get(k))}")
    return co


def policy_text(rules):
    return fill(rules["cancel_policy_text"], horas_cancelar=f"{rules['cancel_hours']:g}", horas_reprogramar=f"{rules['reschedule_hours']:g}",
                max_reprogramaciones=rules["max_reschedules"])


def refund_text(rules):
    if rules["deposit_refund"] == "none":
        return "El anticipo no es reembolsable."
    late = f"se reembolsa el {rules['deposit_refund_pct']:g} %" if rules["deposit_refund"] == "partial" else "no es reembolsable"
    if not rules["cancel_enabled"]:
        return "El anticipo es reembolsable si cancela."
    return f"El anticipo se reembolsa completo si cancela con al menos {rules['cancel_hours']:g} horas; después {late}."


def bank_text(rules):
    parts = [f"Banco: {rules['bank_name']}" if rules["bank_name"] else "", f"Cuenta: {rules['bank_account']}" if rules["bank_account"] else "",
             f"A nombre de: {rules['bank_holder']}" if rules["bank_holder"] else "", rules["bank_message"],
             f"Envíe el comprobante al WhatsApp {rules['deposit_whatsapp']}." if rules["deposit_whatsapp"] else ""]
    return " · ".join(p for p in parts if p) or "El salón le enviará los datos para transferir."


def public_rules(rules):
    return {"cancel_enabled": rules["cancel_enabled"], "policy_text": policy_text(rules) if rules["cancel_enabled"] else "",
            "cancel_hours": rules["cancel_hours"], "reschedule_hours": rules["reschedule_hours"], "max_reschedules": rules["max_reschedules"],
            "deposit_enabled": rules["deposit_enabled"], "deposit_hours": rules["deposit_hours"],
            "bank_text": bank_text(rules) if rules["deposit_enabled"] else "", "refund_text": refund_text(rules) if rules["deposit_enabled"] else "",
            "min_advance_hours": rules["min_advance_hours"], "max_advance_days": rules["max_advance_days"]}


async def fault_count(client_id, rules):
    q = {"client_id": client_id, "status": "no_show"}
    if int(rules["noshow_months"]):
        q["date"] = {"$gte": (local_now() - timedelta(days=30 * int(rules["noshow_months"]))).strftime("%Y-%m-%d")}
    return await db.appointments.count_documents(q)


def deposit_amount(rules, svc, minutes, price, faults_over=False, flagged=False):
    if not rules["deposit_enabled"]:
        return 0
    if float(svc.get("deposit") or 0) > 0:
        return float(svc["deposit"])
    w = rules["deposit_when"]
    trig = (("duration" in w and minutes >= int(rules["deposit_min_minutes"])) or ("price" in w and price >= float(rules["deposit_min_price"]))
            or ("services" in w and svc["id"] in rules["deposit_service_ids"]) or flagged
            or (faults_over and ("no_shows" in w or (rules["noshow_enabled"] and rules["noshow_action"] == "alert_deposit"))))
    if not trig:
        return 0
    if rules["deposit_type"] == "fixed":
        return round(min(float(rules["deposit_fixed"]), price), 2)
    return round(price * float(rules["deposit_percent"]) / 100, 2)


@r.get("/salon-rules")
async def get_rules(branch_id: str = "", c=Depends(guard(ALL_STAFF))):
    co = c["company"]
    return {"groups": GROUPS, "schema": list(DEFS.values()), "suggested": suggested(co.get("country")), "company": co.get("rules") or {},
            "branch": (co.get("branch_rules") or {}).get(branch_id, {}) if branch_id else {}, "effective": effective(co, branch_id or None),
            "can_edit": c["user"]["role"] in ADMIN + ("super_admin",), "reviewed": bool(co.get("rules_reviewed")),
            "branches": [{"id": b["id"], "name": b["name"]} for b in await find("branches", {"company_id": c["cid"]})]}


@r.put("/salon-rules")
async def put_rules(body: dict = Body(...), c=Depends(guard(ADMIN))):
    co = await save_rules(c, body.get("values") or {}, body.get("branch_id") or None)
    return await get_rules(body.get("branch_id") or "", {**c, "company": co})


@r.post("/salon-rules/reset")
async def reset_rules(body: dict = Body(default={}), c=Depends(guard(ADMIN))):
    bid = body.get("branch_id") or None
    cur = (c["company"].get("branch_rules") or {}).get(bid, {}) if bid else c["company"].get("rules") or {}
    if bid:
        await save_rules(c, {k: None for k in cur}, bid)
    else:
        await save_rules(c, {k: d["suggested"] for k, d in DEFS.items()}, None)
        await db.companies.update_one({"id": c["cid"]}, {"$set": {"rules": {}}})
    await audit(c["user"], c["cid"], "rule_reset", "reglas", f"Restaurar sugeridos ({'sucursal' if bid else 'general'})")
    return {"ok": True}


@r.post("/salon-rules/reviewed")
async def rules_reviewed(c=Depends(guard(ADMIN))):
    await db.companies.update_one({"id": c["cid"]}, {"$set": {"rules_reviewed": True}})
    return {"ok": True}
