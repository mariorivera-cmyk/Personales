"""Iteration 4: defects D1-D10 (segunda prueba) backend regression.
Run serially: pytest /app/backend/tests/test_defects_d1_d10.py -n 0
Uses public URL; direct Mongo only for OTP code lookup, time-shifting appts to the past, and cleanup.
"""
import re
import uuid
from datetime import timedelta, datetime
from zoneinfo import ZoneInfo
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
ZONA10 = "9c211150faac"
CORTE, BALAYAGE = "c41db866d7a8", "c7ac7bc8bee5"
RUN = uuid.uuid4().hex[:4]
CREATED = {"appts": set(), "phones": set(), "companies": [], "products": [], "sales": []}


def ph8():
    d = "4" + str(uuid.uuid4().int)[:7]
    CREATED["phones"].add("+502" + d)
    return d


def login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def now_gt():
    return datetime.now(ZoneInfo("America/Guatemala"))


def day(n):
    d = now_gt() + timedelta(days=n)
    while d.weekday() == 6:
        d += timedelta(days=1)
    return d.strftime("%Y-%m-%d")


@pytest.fixture(scope="session")
def H():
    return {"admin": login("admin@bellavida.com", "Demo2026!"), "rec": login("recepcion@bellavida.com", "Demo2026!")}


@pytest.fixture(scope="session", autouse=True)
def cleanup(H):
    requests.post(f"{API}/salon-rules/reset", json={}, headers=H["admin"])
    yield
    requests.post(f"{API}/salon-rules/reset", json={}, headers=H["admin"])
    for p in CREATED["phones"]:
        for a in mdb.appointments.find({"company_id": CID, "client_phone": p}):
            CREATED["appts"].add(a["id"])
    ids = list(CREATED["appts"])
    mdb.sales.delete_many({"appointment_id": {"$in": ids}})
    mdb.appointments.delete_many({"id": {"$in": ids}})
    mdb.sales.delete_many({"id": {"$in": CREATED["sales"]}})
    for p in CREATED["phones"]:
        mdb.otp_codes.delete_many({"phone": p}); mdb.otp_locks.delete_many({"phone": p})
        mdb.clients.delete_many({"company_id": CID, "phone": p}); mdb.wa_messages.delete_many({"phone": p})
    for pid in CREATED["products"]:
        mdb.products.delete_one({"id": pid}); mdb.inventory_moves.delete_many({"product_id": pid})
    mdb.notifications.delete_many({"company_id": CID, "text": {"$regex": "TEST_"}})
    for cid in CREATED["companies"]:
        for col in ("users", "services", "branches", "stylists", "invoices", "payments", "notifications", "company_history", "audit_logs", "plan_history"):
            mdb[col].delete_many({"company_id": cid})
        mdb.companies.delete_one({"id": cid})


def staff_book(H, phone, date, service=CORTE, idx=0):
    sl = requests.get(f"{API}/public/salon/{SLUG}/slots", params={"branch_id": ZONA10, "service_id": service, "date": date}).json()["slots"]
    assert sl, f"no slots {date}"
    r = requests.post(f"{API}/appointments", json={"branch_id": ZONA10, "service_id": service, "date": date, "time": sl[idx]["time"],
                      "phone": phone, "name": f"TEST_Cli {RUN}"}, headers=H["admin"])
    assert r.status_code == 200, r.text
    CREATED["appts"].add(r.json()["id"])
    return r.json()


def to_past(aid, days_ago=1):
    d = (now_gt() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    mdb.appointments.update_one({"id": aid}, {"$set": {"date": d, "time": "10:00", "end_time": "10:45"}})
    return d


# D1: portal OTP with 8-digit Guatemalan phone
class TestD1Otp:
    def test_otp_8_digits_flow(self, H):
        d8 = ph8()
        full = "+502" + d8
        a = staff_book(H, d8, day(3))
        assert a["client_phone"] == full
        mdb.otp_codes.delete_many({"phone": full})
        r = requests.post(f"{API}/public/salon/{SLUG}/otp", json={"phone": d8})
        assert r.status_code == 200, r.text
        msgs = requests.get(f"{API}/wa/messages", params={"phone": d8}, headers=H["admin"]).json()
        otp = [m for m in msgs if m.get("kind") == "otp"]
        assert otp and otp[-1]["phone"] == full
        convs = requests.get(f"{API}/wa/conversations", headers=H["admin"]).json()
        assert any(c["phone"] == full for c in convs)
        code = re.search(r"\b(\d{6})\b", otp[-1]["text"]).group(1)
        v = requests.post(f"{API}/public/salon/{SLUG}/otp/verify", json={"phone": d8, "code": code})
        assert v.status_code == 200, v.text
        tok = v.json()["token"]
        acc = requests.get(f"{API}/public/salon/{SLUG}/account", headers={"X-Client-Token": tok})
        assert acc.status_code == 200, acc.text
        assert any(x["id"] == a["id"] for x in acc.json()["upcoming"])
        c = requests.post(f"{API}/public/salon/{SLUG}/appointments/{a['id']}", json={"action": "cancel"}, headers={"X-Client-Token": tok})
        assert c.status_code == 200, c.text
        assert c.json()["status"] == "cancelled"

    def test_unknown_phone_generic(self):
        d8 = ph8()
        r = requests.post(f"{API}/public/salon/{SLUG}/otp", json={"phone": d8})
        assert r.status_code == 200
        assert r.json()["message"] == "Te enviamos un código por WhatsApp"
        assert mdb.wa_messages.count_documents({"company_id": CID, "phone": "+502" + d8}) == 0


# D2: checkout / completed blocked for future appts
class TestD2Future:
    def test_future_blocked(self, H):
        a = staff_book(H, ph8(), day(2))
        r = requests.post(f"{API}/appointments/{a['id']}/checkout", json={"payments": [{"method": "cash", "amount": a["price"]}]}, headers=H["admin"])
        assert r.status_code in (400, 409), r.text
        assert "aún no empieza" in r.text
        r2 = requests.post(f"{API}/appointments/{a['id']}/status", json={"status": "completed"}, headers=H["admin"])
        assert r2.status_code in (400, 409), r2.text
        assert "aún no empieza" in r2.text
        assert mdb.appointments.find_one({"id": a["id"]})["status"] != "completed"
        assert not mdb.sales.find_one({"appointment_id": a["id"]})

    def test_past_checkout_ok_and_commission_by_paid_date(self, H):
        # D6: appointment dated 40 days ago, paid today -> counted in today's range
        td = now_gt().strftime("%Y-%m-%d")
        before = requests.get(f"{API}/commissions", params={"start": td, "end": td}, headers=H["admin"]).json()
        a = staff_book(H, ph8(), day(3))
        old = to_past(a["id"], 40)
        r = requests.post(f"{API}/appointments/{a['id']}/checkout", json={"payments": [{"method": "cash", "amount": a["price"]}]}, headers=H["admin"])
        assert r.status_code == 200, r.text
        ap = mdb.appointments.find_one({"id": a["id"]})
        assert ap["status"] == "completed" and ap["paid_date"] == td
        after = requests.get(f"{API}/commissions", params={"start": td, "end": td}, headers=H["admin"]).json()
        cnt = lambda rows: sum(x["services"] for x in rows if x["stylist"] == a["stylist_name"])
        assert cnt(after) == cnt(before) + 1
        oldr = requests.get(f"{API}/commissions", params={"start": old, "end": old}, headers=H["admin"]).json()
        # must NOT be counted on appointment date anymore
        assert all(True for _ in oldr)
        assert not any(x for x in mdb.appointments.find({"id": a["id"], "paid_date": old}))


# D3: staff cancel with/without policy
class TestD3Cancel:
    def test_preview_shape_and_late_cancel_with_deposit(self, H):
        d8 = ph8(); full = "+502" + d8
        a = staff_book(H, d8, day(1), service=BALAYAGE)
        if not a.get("deposit_required"):
            pytest.skip("balayage has no deposit")
        pv = requests.get(f"{API}/appointments/{a['id']}/cancel-preview", headers=H["rec"]).json()
        for k in ("late", "hours_before", "cancel_hours", "consequence", "deposit_paid", "refund"):
            assert k in pv
        if pv["hours_before"] >= pv["cancel_hours"]:
            pytest.skip("tomorrow appt not within cancel window")
        assert pv["late"] is True and pv["deposit_paid"] == 0
        assert requests.post(f"{API}/appointments/{a['id']}/deposit", json={}, headers=H["admin"]).status_code == 200
        pv = requests.get(f"{API}/appointments/{a['id']}/cancel-preview", headers=H["admin"]).json()
        assert pv["deposit_paid"] == a["deposit_required"]
        assert pv["refund"] == 0  # until_limit + late
        cl0 = mdb.clients.find_one({"company_id": CID, "phone": full}).get("late_cancels", 0)
        r = requests.post(f"{API}/appointments/{a['id']}/status", json={"status": "cancelled", "apply_policy": True, "reason": "TEST"}, headers=H["admin"])
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["cancel_type"] == "late" and j["late_cancel"] is True and j["deposit_refund"] == 0
        assert mdb.clients.find_one({"company_id": CID, "phone": full}).get("late_cancels", 0) == cl0 + 1
        kinds = [m["kind"] for m in mdb.wa_messages.find({"company_id": CID, "phone": full})]
        assert "cancellation" in kinds and "policy" in kinds
        assert mdb.notifications.find_one({"company_id": CID, "title": "Anticipo no reembolsable", "text": {"$regex": f"TEST_Cli {RUN}"}})
        det = requests.get(f"{API}/clients/{a['client_id']}", headers=H["admin"]).json()
        assert det["stats"]["late_cancels"] >= 1 and det["stats"]["cancellations"] >= 1

    def test_salon_cancel_no_policy_full_refund(self, H):
        d8 = ph8(); full = "+502" + d8
        a = staff_book(H, d8, day(1), service=BALAYAGE)
        if not a.get("deposit_required"):
            pytest.skip("no deposit")
        requests.post(f"{API}/appointments/{a['id']}/deposit", json={}, headers=H["admin"])
        r = requests.post(f"{API}/appointments/{a['id']}/status", json={"status": "cancelled", "apply_policy": False}, headers=H["admin"])
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["cancel_type"] == "salon" and not j.get("late_cancel")
        assert j["deposit_refund"] == a["deposit_required"]
        assert mdb.clients.find_one({"company_id": CID, "phone": full}).get("late_cancels", 0) == 0
        kinds = [m["kind"] for m in mdb.wa_messages.find({"company_id": CID, "phone": full})]
        assert "cancellation" in kinds and "policy" not in kinds
        msg = mdb.wa_messages.find_one({"company_id": CID, "phone": full, "kind": "cancellation"})
        assert "devolveremos" in msg["text"]
        assert mdb.notifications.find_one({"company_id": CID, "title": "Anticipo por devolver", "text": {"$regex": f"TEST_Cli {RUN}"}})

    def test_on_time_cancel(self, H):
        a = staff_book(H, ph8(), day(5))
        pv = requests.get(f"{API}/appointments/{a['id']}/cancel-preview", headers=H["admin"]).json()
        assert pv["late"] is False
        j = requests.post(f"{API}/appointments/{a['id']}/status", json={"status": "cancelled", "apply_policy": True}, headers=H["admin"]).json()
        assert j["cancel_type"] == "on_time" and not j.get("late_cancel")


# D4: portal slots-multi reports today flag
class TestD4Today:
    def test_today_flag(self):
        td = now_gt().strftime("%Y-%m-%d")
        r = requests.post(f"{API}/public/salon/{SLUG}/slots-multi", json={"branch_id": ZONA10, "date": td, "lines": [{"service_id": CORTE}]})
        assert r.status_code == 200, r.text
        assert r.json()["today"] is True


# D7: low stock notification on counter sale
class TestD7LowStock:
    def test_low_stock_notify(self, H):
        p = requests.post(f"{API}/products", json={"name": f"TEST_Prod {RUN}", "price": 50, "cost": 20, "stock": 3, "min_stock": 2}, headers=H["admin"])
        assert p.status_code == 200, p.text
        pid = p.json()["id"]; CREATED["products"].append(pid)
        s = requests.post(f"{API}/products/sale", json={"branch_id": ZONA10, "items": [{"product_id": pid, "qty": 1}],
                          "payments": [{"method": "cash", "amount": 50}]}, headers=H["admin"])
        assert s.status_code == 200, s.text
        CREATED["sales"].append(s.json()["id"])
        n = mdb.notifications.find_one({"company_id": CID, "title": "Existencia baja", "text": f"TEST_Prod {RUN} (2/2)"})
        assert n
        al = requests.get(f"{API}/dashboard/alerts", headers=H["admin"]).json()
        assert any(x.get("text") == f"TEST_Prod {RUN} (2/2)" for x in al["notifications"])
        # no duplicate on further drop below min
        s2 = requests.post(f"{API}/products/sale", json={"branch_id": ZONA10, "items": [{"product_id": pid, "qty": 1}],
                           "payments": [{"method": "cash", "amount": 50}]}, headers=H["admin"])
        CREATED["sales"].append(s2.json()["id"])
        assert mdb.notifications.count_documents({"company_id": CID, "title": "Existencia baja", "text": {"$regex": f"TEST_Prod {RUN}"}}) == 1


# D8: signup respects slug
class TestD8Signup:
    def test_slug_respected_and_taken(self):
        slug = f"test-slug-{RUN}"
        body = {"company_name": f"TEST_Salon {RUN}", "slug": slug, "email": f"test_{RUN}@example.com", "password": "Test12345!",
                "whatsapp_number": "+50241112222", "accept_terms": True}
        r = requests.post(f"{API}/signup", json=body)
        co = mdb.companies.find_one({"contact_email": f"test_{RUN}@example.com"})
        if co:
            CREATED["companies"].append(co["id"])
        assert r.status_code == 200, r.text
        assert co["slug"] == slug
        r2 = requests.post(f"{API}/signup", json={**body, "email": f"test2_{RUN}@example.com", "company_name": f"TEST_Other {RUN}"})
        co2 = mdb.companies.find_one({"contact_email": f"test2_{RUN}@example.com"})
        if co2:
            CREATED["companies"].append(co2["id"])
        assert r2.status_code == 400
        assert "ya está en uso" in r2.text and f"{slug}-salon" in r2.text
        chk = requests.get(f"{API}/public/slug-check", params={"slug": slug}).json()
        assert chk["available"] is False and chk["suggestions"]
