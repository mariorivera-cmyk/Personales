"""Iteration 3: R21 'Panel de reglas del salón' (/api/salon-rules) backend regression.
Uses public URL from frontend/.env; direct Mongo only for OTP codes, time-shifting test appts (no-show), and cleanup.
"""
import re
import uuid
from datetime import timedelta, datetime
import pytest
import requests
from pymongo import MongoClient
from dotenv import dotenv_values

for line in open("/app/frontend/.env"):
    if line.startswith("REACT_APP_BACKEND_URL"):
        BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
API = f"{BASE_URL}/api"
SLUG = "bellavida"
BENV = dotenv_values("/app/backend/.env")
mdb = MongoClient(BENV["MONGO_URL"])[BENV["DB_NAME"]]
CID = mdb.companies.find_one({"slug": SLUG})["id"]
ZONA10, CAYALA = "9c211150faac", "712802e9f868"
CORTE, BALAYAGE, MASCARILLA = "c41db866d7a8", "c7ac7bc8bee5", "17f399d32a39"
RUN = uuid.uuid4().hex[:4]
CREATED = {"appts": set(), "phones": set(), "companies": []}


def ph():
    p = "+5024" + str(uuid.uuid4().int)[:7]
    CREATED["phones"].add(p)
    return p


def login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def local_today():
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/Guatemala"))


def day(n):
    return (local_today() + timedelta(days=n)).strftime("%Y-%m-%d")


def next_weekday_at_least(n):
    d = local_today() + timedelta(days=n)
    while d.weekday() == 6:
        d += timedelta(days=1)
    return d.strftime("%Y-%m-%d")


@pytest.fixture(scope="session")
def H():
    return {"admin": login("admin@bellavida.com", "Demo2026!"), "rec": login("recepcion@bellavida.com", "Demo2026!")}


def put(H, values, branch_id=None, who="admin"):
    body = {"values": values}
    if branch_id:
        body["branch_id"] = branch_id
    return requests.put(f"{API}/salon-rules", json=body, headers=H[who])


def reset(H):
    requests.post(f"{API}/salon-rules/reset", json={}, headers=H["admin"])
    for b in (ZONA10, CAYALA):
        requests.post(f"{API}/salon-rules/reset", json={"branch_id": b}, headers=H["admin"])


@pytest.fixture(scope="session", autouse=True)
def cleanup(H):
    reset(H)
    yield
    reset(H)
    rv = mdb.companies.find_one({"id": CID})
    print("final rules:", rv.get("rules"), rv.get("branch_rules"))
    for p in CREATED["phones"]:
        for a in mdb.appointments.find({"company_id": CID, "client_phone": p}):
            CREATED["appts"].add(a["id"])
    ids = list(CREATED["appts"])
    mdb.sales.delete_many({"appointment_id": {"$in": ids}})
    mdb.appointments.delete_many({"id": {"$in": ids}})
    for p in CREATED["phones"]:
        mdb.otp_codes.delete_many({"phone": p}); mdb.otp_locks.delete_many({"phone": p})
        mdb.clients.delete_many({"company_id": CID, "phone": p}); mdb.wa_messages.delete_many({"phone": p})
    mdb.notifications.delete_many({"company_id": CID, "text": {"$regex": "TEST_"}})
    for cid in CREATED["companies"]:
        for col in ("users", "services", "branches", "stylists", "invoices", "payments", "notifications", "company_history", "audit_logs"):
            mdb[col].delete_many({"company_id": cid})
        mdb.companies.delete_one({"id": cid})


def staff_book(H, phone, date, service=CORTE, branch=ZONA10, idx=0):
    sl = requests.get(f"{API}/public/salon/{SLUG}/slots", params={"branch_id": branch, "service_id": service, "date": date}).json()["slots"]
    assert sl, f"no slots {date}"
    r = requests.post(f"{API}/appointments", json={"branch_id": branch, "service_id": service, "date": date, "time": sl[idx]["time"],
                      "phone": phone, "name": f"TEST_Cli {RUN}"}, headers=H["admin"])
    assert r.status_code == 200, r.text
    CREATED["appts"].add(r.json()["id"])
    return r.json()


def portal_book(phone, date, service=CORTE, branch=ZONA10, idx=0):
    sl = requests.get(f"{API}/public/salon/{SLUG}/slots", params={"branch_id": branch, "service_id": service, "date": date}).json()["slots"]
    if not sl:
        return None
    r = requests.post(f"{API}/public/salon/{SLUG}/book", json={"branch_id": branch, "service_id": service, "date": date,
                      "time": sl[min(idx, len(sl) - 1)]["time"], "phone": phone, "name": f"TEST_Cli {RUN}"})
    if r.status_code == 200:
        CREATED["appts"].add(r.json()["id"])
    return r


def client_token(phone):
    mdb.otp_codes.delete_many({"phone": phone}); mdb.otp_locks.delete_many({"phone": phone})
    requests.post(f"{API}/public/salon/{SLUG}/otp", json={"phone": phone})
    m = mdb.wa_messages.find_one({"company_id": CID, "phone": phone, "kind": "otp"}, sort=[("created_at", -1)])
    code = re.search(r"\b(\d{6})\b", m["text"]).group(1)
    return requests.post(f"{API}/public/salon/{SLUG}/otp/verify", json={"phone": phone, "code": code}).json()["token"]


# ---------- GET schema / permissions ----------
class TestSchema:
    def test_get_admin(self, H):
        d = requests.get(f"{API}/salon-rules", headers=H["admin"]).json()
        assert set(d["groups"]) == set("ABCDEF")
        assert len(d["schema"]) == 42, len(d["schema"])
        assert all("suggested" in s and "desc" in s and "label" in s for s in d["schema"])
        assert d["can_edit"] is True and len(d["branches"]) == 2
        e = d["effective"]
        assert e["cancel_hours"] == 24 and e["deposit_percent"] == 30 and e["slot_interval"] == 30 and e["reminder_hours"] == [24, 2]

    def test_get_receptionist_readonly(self, H):
        d = requests.get(f"{API}/salon-rules", headers=H["rec"])
        assert d.status_code == 200 and d.json()["can_edit"] is False
        r = put(H, {"cancel_hours": 10}, who="rec")
        assert r.status_code == 403

    @pytest.mark.parametrize("vals,msg", [({"deposit_percent": 150}, "porcentaje no puede ser mayor a 100"),
                                          ({"cancel_hours": ""}, "no puede quedar vacío"),
                                          ({"cancel_hours": -3}, "no puede ser negativo"),
                                          ({"slot_interval": 20}, "opción no válida"),
                                          ({"max_reschedules": 1.5}, "entero"),
                                          ({"reminder_hours": [0]}, "entre 1 y 168"),
                                          ({"cancel_policy_text": "  "}, "no puede quedar vacío")])
    def test_validation(self, H, vals, msg):
        r = put(H, vals)
        assert r.status_code == 400, r.text
        assert msg in r.text, r.text


# ---------- Audit + reset ----------
class TestAuditReset:
    def test_change_audited_and_reset(self, H):
        r = put(H, {"cancel_hours": 30, "deposit_enabled": False})
        assert r.status_code == 200
        print("PUT response effective cancel_hours (stale?):", r.json()["effective"]["cancel_hours"])
        assert requests.get(f"{API}/salon-rules", headers=H["admin"]).json()["effective"]["cancel_hours"] == 30
        logs = requests.get(f"{API}/audit", headers=H["admin"]).json()
        rl = [x["detail"] for x in logs if x["action"] == "rule_change" and x["entity"] == "reglas"][:5]
        print("audit:", rl)
        assert any(d.startswith("[General] Horas mínimas para cancelar sin costo: 24 → 30") for d in rl)
        assert any("[General] Anticipo: Sí → No" in d for d in rl)
        assert requests.post(f"{API}/salon-rules/reset", json={}, headers=H["admin"]).status_code == 200
        e = requests.get(f"{API}/salon-rules", headers=H["admin"]).json()
        assert e["effective"]["cancel_hours"] == 24 and e["effective"]["deposit_enabled"] is True and e["company"] == {}

    def test_reset_receptionist_forbidden(self, H):
        assert requests.post(f"{API}/salon-rules/reset", json={}, headers=H["rec"]).status_code == 403


# ---------- Branch override + public ----------
class TestBranch:
    def test_branch_override_public_and_quote(self, H):
        r = put(H, {"cancel_hours": 6}, CAYALA)
        assert r.status_code == 200, r.text
        g = requests.get(f"{API}/salon-rules", params={"branch_id": CAYALA}, headers=H["admin"]).json()
        assert g["branch"] == {"cancel_hours": 6} and g["effective"]["cancel_hours"] == 6
        logs = requests.get(f"{API}/audit", headers=H["admin"]).json()
        assert any(x["detail"].startswith("[Sucursal Cayalá]") for x in logs[:5] if x["action"] == "rule_change")
        p = requests.get(f"{API}/public/salon/{SLUG}").json()
        assert p["rules"]["cancel_hours"] == 24 and p["branch_rules"][CAYALA]["cancel_hours"] == 6
        assert p["branch_rules"][ZONA10]["cancel_hours"] == 24
        assert "6 horas" in p["branch_rules"][CAYALA]["policy_text"] and "24 horas" in p["rules"]["policy_text"]
        q = requests.post(f"{API}/public/salon/{SLUG}/quote", json={"branch_id": CAYALA, "service_ids": [BALAYAGE], "phone": ph()}).json()
        assert q["rules"]["cancel_hours"] == 6 and q["deposit"] == 360 and q["blocked"] is False
        # branch reset removes overrides
        assert requests.post(f"{API}/salon-rules/reset", json={"branch_id": CAYALA}, headers=H["admin"]).status_code == 200
        g = requests.get(f"{API}/salon-rules", params={"branch_id": CAYALA}, headers=H["admin"]).json()
        assert g["branch"] == {} and g["effective"]["cancel_hours"] == 24


# ---------- Deposit toggle ----------
class TestDeposit:
    def test_disable_deposit(self, H):
        put(H, {"deposit_enabled": False})
        q = requests.post(f"{API}/public/salon/{SLUG}/quote", json={"branch_id": ZONA10, "service_ids": [BALAYAGE]}).json()
        assert q["deposit"] == 0 and q["rules"]["deposit_enabled"] is False and q["rules"]["bank_text"] == ""
        r = portal_book(ph(), next_weekday_at_least(3), BALAYAGE)
        assert r is not None and r.status_code == 200, r and r.text
        assert r.json()["deposit_required"] == 0
        put(H, {"deposit_enabled": True})
        q = requests.post(f"{API}/public/salon/{SLUG}/quote", json={"branch_id": ZONA10, "service_ids": [BALAYAGE]}).json()
        assert q["deposit"] == 360


# ---------- Snapshot ----------
class TestSnapshot:
    def test_snapshot_and_late_cancel_uses_snapshot(self, H):
        p = ph()
        a = staff_book(H, p, day(1))  # tomorrow, < 24h ahead
        assert a["rules"]["cancel_hours"] == 24
        put(H, {"cancel_hours": 2})
        doc = mdb.appointments.find_one({"id": a["id"]})
        assert doc["rules"]["cancel_hours"] == 24
        tok = client_token(p)
        r = requests.post(f"{API}/public/salon/{SLUG}/appointments/{a['id']}", json={"action": "cancel", "reason": "TEST"}, headers={"X-Client-Token": tok})
        assert r.status_code == 200, r.text
        assert mdb.appointments.find_one({"id": a["id"]}).get("late_cancel") is True
        m = mdb.wa_messages.find_one({"phone": p, "kind": "policy"}, sort=[("created_at", -1)])
        assert m and "24 horas" in m["text"], m
        put(H, {"cancel_hours": None})


# ---------- No-shows ----------
class TestNoShow:
    def test_noshow_tolerance_limit_and_block(self, H):
        put(H, {"noshow_limit": 1})
        p = ph()
        a = staff_book(H, p, day(2))
        now = local_today()
        past = (now - timedelta(minutes=60))
        mdb.appointments.update_one({"id": a["id"]}, {"$set": {"date": past.strftime("%Y-%m-%d"), "time": past.strftime("%H:%M")}})
        b = staff_book(H, p, day(2), idx=3)
        near = now - timedelta(minutes=5)
        mdb.appointments.update_one({"id": b["id"]}, {"$set": {"date": near.strftime("%Y-%m-%d"), "time": near.strftime("%H:%M")}})
        r = requests.post(f"{API}/appointments/{b['id']}/status", json={"status": "no_show"}, headers=H["admin"])
        assert r.status_code == 409, r.text
        assert "tolerancia" in r.text
        r = requests.post(f"{API}/appointments/{a['id']}/status", json={"status": "no_show"}, headers=H["admin"])
        assert r.status_code == 200, r.text
        al = requests.get(f"{API}/dashboard/alerts", headers=H["admin"]).json()
        assert any(n.get("title") == "Límite de faltas superado" for n in al["notifications"]), [n.get("title") for n in al["notifications"]]
        lk = requests.get(f"{API}/clients/lookup", params={"phone": p}, headers=H["admin"]).json()
        assert lk["alert"] is True and lk["no_shows"] == 1
        # alert_deposit (default) -> quote deposit on a non-deposit service
        q = requests.post(f"{API}/public/salon/{SLUG}/quote", json={"branch_id": ZONA10, "service_ids": [CORTE], "phone": p}).json()
        assert q["deposit"] == 45 and q["blocked"] is False, q
        put(H, {"noshow_action": "block"})
        q = requests.post(f"{API}/public/salon/{SLUG}/quote", json={"branch_id": ZONA10, "service_ids": [CORTE], "phone": p}).json()
        assert q["blocked"] is True
        r = portal_book(p, next_weekday_at_least(4))
        assert r.status_code == 409 and "No es posible reservar en línea" in r.text, r.text
        mdb.notifications.delete_many({"company_id": CID, "title": "Límite de faltas superado", "body": {"$regex": f"TEST_Cli {RUN}"}})
        put(H, {"noshow_limit": None, "noshow_action": None})


# ---------- Booking limits (public only) ----------
class TestBookingLimits:
    def test_max_active_public_only(self, H):
        put(H, {"max_active_per_client": 1})
        p = ph()
        d = next_weekday_at_least(5)
        assert portal_book(p, d, idx=0).status_code == 200
        r = portal_book(p, d, idx=6)
        assert r.status_code == 409 and "máximo permitido es 1" in r.text, r.text
        staff_book(H, p, d, idx=8)  # staff not limited
        put(H, {"max_active_per_client": None})

    def test_min_and_max_advance(self, H):
        put(H, {"min_advance_hours": 48})
        d1 = day(1)
        pub = requests.get(f"{API}/public/salon/{SLUG}/slots", params={"branch_id": ZONA10, "service_id": CORTE, "date": d1}).json()["slots"]
        assert pub == [], pub[:2]
        put(H, {"min_advance_hours": None, "max_advance_days": 3})
        far = day(10)
        pub = requests.get(f"{API}/public/salon/{SLUG}/slots", params={"branch_id": ZONA10, "service_id": CORTE, "date": far}).json()["slots"]
        assert pub == []
        r = requests.post(f"{API}/appointments", json={"branch_id": ZONA10, "service_id": CORTE, "date": next_weekday_at_least(10), "time": "10:00",
                          "phone": ph(), "name": f"TEST_Cli {RUN}"}, headers=H["admin"])
        assert r.status_code == 200, r.text  # staff unaffected
        CREATED["appts"].add(r.json()["id"])
        put(H, {"max_advance_days": None})

    def test_slot_interval(self, H):
        d = next_weekday_at_least(6)
        put(H, {"slot_interval": 15})
        times = sorted({s["time"] for s in requests.get(f"{API}/public/salon/{SLUG}/slots", params={"branch_id": ZONA10, "service_id": CORTE, "date": d}).json()["slots"]})
        assert any(t.endswith(":15") or t.endswith(":45") for t in times), times[:6]
        put(H, {"slot_interval": "60"})
        times = {s["time"] for s in requests.get(f"{API}/public/salon/{SLUG}/slots", params={"branch_id": ZONA10, "service_id": CORTE, "date": d}).json()["slots"]}
        assert times and all(t.endswith(":00") for t in times), sorted(times)[:6]
        put(H, {"slot_interval": None})


# ---------- Client reschedule ----------
class TestReschedule:
    def test_reschedule_limits(self, H):
        put(H, {"max_reschedules": 1})
        p = ph()
        d = next_weekday_at_least(7)
        a = portal_book(p, d).json()
        tok = client_token(p)
        sl = requests.get(f"{API}/public/salon/{SLUG}/slots", params={"branch_id": ZONA10, "service_id": CORTE, "date": d}).json()["slots"]
        u = f"{API}/public/salon/{SLUG}/appointments/{a['id']}"
        r = requests.post(u, json={"action": "reschedule", "date": d, "time": sl[-1]["time"]}, headers={"X-Client-Token": tok})
        assert r.status_code == 200, r.text
        r = requests.post(u, json={"action": "reschedule", "date": d, "time": sl[-3]["time"]}, headers={"X-Client-Token": tok})
        assert r.status_code == 409 and "máximo de 1" in r.text, r.text
        put(H, {"max_reschedules": None})
        # reschedule_hours via snapshot: set 20h before booking tomorrow (~12h ahead)
        put(H, {"reschedule_hours": 20})
        p2 = ph()
        b = staff_book(H, p2, day(1))
        hrs = (datetime.strptime(f"{b['date']} {b['time']}", "%Y-%m-%d %H:%M") - local_today().replace(tzinfo=None)).total_seconds() / 3600
        tok2 = client_token(p2)
        r = requests.post(f"{API}/public/salon/{SLUG}/appointments/{b['id']}", json={"action": "reschedule", "date": d, "time": sl[2]["time"]},
                          headers={"X-Client-Token": tok2})
        print("hours left", hrs, r.status_code, r.text[:200])
        assert hrs < 20 and r.status_code == 409 and "20 horas" in r.text
        put(H, {"reschedule_hours": None})


# ---------- Commission / loyalty / onboarding ----------
class TestMisc:
    def test_checkout_commission_rule(self, H):
        put(H, {"commission_percent": 40})
        a = staff_book(H, ph(), next_weekday_at_least(8))
        # D2: future appts can't be checked out -> shift to the past
        mdb.appointments.update_one({"id": a["id"]}, {"$set": {"date": day(-1)}})
        r = requests.post(f"{API}/appointments/{a['id']}/checkout", json={"tip": 10, "payments": [{"method": "cash", "amount": 160}]}, headers=H["admin"])
        assert r.status_code == 200, r.text
        assert mdb.appointments.find_one({"id": a["id"]})["commission"] == 60.0  # 150*40%, tips excluded
        put(H, {"commission_percent": None})

    def test_loyalty_mapping(self, H):
        lo = requests.get(f"{API}/loyalty", headers=H["admin"]).json()["config"]
        r = requests.put(f"{API}/loyalty", json={**lo, "points_per_100": 15, "redeem_value": 0.2}, headers=H["admin"])
        assert r.status_code == 200, r.text
        e = requests.get(f"{API}/salon-rules", headers=H["admin"]).json()["effective"]
        assert e["loyalty_points_per_100"] == 15 and e["loyalty_redeem_value"] == 0.2
        lo2 = requests.get(f"{API}/loyalty", headers=H["admin"]).json()["config"]
        assert lo2["points_per_100"] == 15
        bad = requests.put(f"{API}/loyalty", json={**lo, "points_per_100": -1}, headers=H["admin"])
        assert bad.status_code == 400, bad.text
        put(H, {"loyalty_points_per_100": None, "loyalty_redeem_value": None})

    def test_onboarding_step(self, H):
        ob = requests.get(f"{API}/onboarding", headers=H["admin"]).json()
        steps = ob.get("steps", ob)
        st = [s for s in steps if s.get("key") == "rules"]
        assert st and st[0]["to"] == "/app/config?tab=reglas"


# ---------- Two salons ----------
class TestTwoSalons:
    def test_second_salon_own_policy(self, H):
        r = requests.post(f"{API}/signup", json={"company_name": f"TEST_Salon Reglas {RUN}", "email": f"test_rules_{RUN}@example.com",
                          "password": "Test2026!", "whatsapp_number": "+50251113333", "modules": ["portal"]})
        assert r.status_code == 200, r.text
        tok = {"Authorization": f"Bearer {r.json()['token']}"}
        cid = r.json()["user"]["company_id"]; CREATED["companies"].append(cid)
        slug = mdb.companies.find_one({"id": cid})["slug"]
        g = requests.get(f"{API}/salon-rules", headers=tok).json()
        assert g["effective"]["cancel_hours"] == 24 and g["can_edit"] is True and g["reviewed"] is False
        ob = requests.get(f"{API}/onboarding", headers=tok).json()
        steps = ob.get("steps", ob)
        assert [s for s in steps if s.get("key") == "rules"][0]["done"] is False
        assert requests.put(f"{API}/salon-rules", json={"values": {"cancel_hours": 2}}, headers=tok).status_code == 200
        ob = requests.get(f"{API}/onboarding", headers=tok).json()
        steps = ob.get("steps", ob)
        assert [s for s in steps if s.get("key") == "rules"][0]["done"] is True
        p2 = requests.get(f"{API}/public/salon/{slug}")
        assert p2.status_code == 200, p2.text
        assert "2 horas" in p2.json()["rules"]["policy_text"]
        p1 = requests.get(f"{API}/public/salon/{SLUG}").json()
        assert "24 horas" in p1["rules"]["policy_text"]


# ---------- Reminders / confirmation messages use configured values ----------
class TestMessages:
    def test_reminder_hours_and_confirmation_policy(self, H):
        put(H, {"reminder_hours": [6], "cancel_hours": 8})
        p1 = ph()
        staff_book(H, p1, day(1), idx=4)
        put(H, {"reminder_hours": [48]})
        p2 = ph()
        staff_book(H, p2, day(1), idx=5)
        requests.post(f"{API}/reminders/run", headers=H["admin"])
        assert not mdb.wa_messages.find_one({"phone": p1, "kind": "reminder"})
        m = mdb.wa_messages.find_one({"phone": p2, "kind": "reminder"})
        assert m and "8 horas" in m["text"], m
        p3 = ph()
        r = portal_book(p3, next_weekday_at_least(3), BALAYAGE, idx=2)
        assert r.status_code == 200, r.text
        c = mdb.wa_messages.find_one({"phone": p3, "kind": "confirmation"})
        print("confirmation:", c["text"])
        assert "8 horas" in c["text"] and "Anticipo requerido: Q360.00" in c["text"]
        put(H, {"reminder_hours": None, "cancel_hours": None})
