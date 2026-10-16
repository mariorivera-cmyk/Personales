"""Iteration 2 regression: SalonFlow v2 requirements (R1-R20) backend.
Uses public URL from frontend/.env. Direct Mongo used only for reading simulated WA OTP codes and cleanup.
"""
import os
import re
import uuid
import asyncio
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
CORTE, TINTE, BALAYAGE = "c41db866d7a8", "ba126f8380fc", "c7ac7bc8bee5"
CARLA = "6a6b2dbb5ee9"  # Diego (eligible for Corte)
DATE = "2026-10-19"  # Monday
RUN = uuid.uuid4().hex[:4]
TEST_PHONE = "+5024" + str(uuid.uuid4().int)[:7]
CREATED = {"appts": [], "phones": [TEST_PHONE], "products": [], "companies": [], "reviews": [], "media": []}


def login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="session")
def H():
    return {"admin": login("admin@bellavida.com", "Demo2026!"), "rec": login("recepcion@bellavida.com", "Demo2026!"),
            "sty": login("estilista@bellavida.com", "Demo2026!")}


@pytest.fixture(scope="session", autouse=True)
def cleanup():
    yield
    ids = CREATED["appts"]
    mdb.sales.delete_many({"appointment_id": {"$in": ids}})
    mdb.appointments.delete_many({"id": {"$in": ids}})
    mdb.reviews.delete_many({"appointment_id": {"$in": ids}})
    for p in CREATED["phones"]:
        mdb.otp_codes.delete_many({"phone": p}); mdb.otp_locks.delete_many({"phone": p})
        mdb.clients.delete_many({"company_id": CID, "phone": p}); mdb.wa_messages.delete_many({"phone": p})
        mdb.data_requests.delete_many({"phone": p})
    mdb.otp_codes.delete_many({"phone": "+50250006666", "cid": CID})
    for pid in CREATED["products"]:
        mdb.products.delete_many({"id": pid}); mdb.inventory_moves.delete_many({"product_id": pid})
        mdb.sales.delete_many({"items.product_id": pid})
    for cid in CREATED["companies"]:
        for col in ("users", "services", "branches", "stylists", "invoices", "payments", "notifications", "company_history", "audit"):
            mdb[col].delete_many({"company_id": cid})
        mdb.companies.delete_one({"id": cid})
    mdb.media.delete_many({"id": {"$in": CREATED["media"]}})
    mdb.notifications.delete_many({"company_id": CID, "text": {"$regex": "TEST_|" + "|".join(re.escape(p) for p in CREATED["phones"])}})


def otp_code(phone):
    m = mdb.wa_messages.find_one({"company_id": CID, "phone": phone, "kind": "otp"}, sort=[("created_at", -1)])
    return re.search(r"\b(\d{6})\b", m["text"]).group(1) if m else None


# ---------- R1 OTP ----------
class TestOTP:
    def test_same_response_unknown_and_known(self):
        a = requests.post(f"{API}/public/salon/{SLUG}/otp", json={"phone": TEST_PHONE})
        b = requests.post(f"{API}/public/salon/{SLUG}/otp", json={"phone": "+50250006666"})
        assert a.status_code == b.status_code == 200 and a.json() == b.json()
        assert otp_code(TEST_PHONE) is None  # unknown number receives nothing
        assert otp_code("+50250006666")

    def test_verify_and_account(self):
        code = otp_code("+50250006666")
        bad = requests.post(f"{API}/public/salon/{SLUG}/otp/verify", json={"phone": "+50250006666", "code": "000000" if code != "000000" else "111111"})
        assert bad.status_code == 400
        r = requests.post(f"{API}/public/salon/{SLUG}/otp/verify", json={"phone": "+50250006666", "code": code})
        assert r.status_code == 200 and r.json()["token"]
        acc = requests.get(f"{API}/public/salon/{SLUG}/account", headers={"X-Client-Token": r.json()["token"]})
        assert acc.status_code == 200
        d = acc.json()
        assert d["phone"] == "+50250006666" and len(d["past"]) > 0 and "points" in d
        # code reuse fails
        assert requests.post(f"{API}/public/salon/{SLUG}/otp/verify", json={"phone": "+50250006666", "code": code}).status_code == 400

    def test_no_token_401(self):
        assert requests.get(f"{API}/public/salon/{SLUG}/account").status_code == 401
        assert requests.post(f"{API}/public/salon/{SLUG}/appointments/xyz", json={"action": "cancel"}).status_code == 401
        assert requests.get(f"{API}/public/salon/{SLUG}/account", headers={"X-Client-Token": "bad"}).status_code == 401

    def test_lock_after_5_wrong(self):
        ph = "+5025" + str(uuid.uuid4().int)[:7]; CREATED["phones"].append(ph)
        requests.post(f"{API}/public/salon/{SLUG}/otp", json={"phone": ph})
        codes = [requests.post(f"{API}/public/salon/{SLUG}/otp/verify", json={"phone": ph, "code": "12345"}).status_code for _ in range(6)]
        assert codes[:5] == [400] * 5 and codes[5] == 429, codes

    def test_max_3_sends_per_hour(self):
        ph = "+5025" + str(uuid.uuid4().int)[:7]; CREATED["phones"].append(ph)
        codes = [requests.post(f"{API}/public/salon/{SLUG}/otp", json={"phone": ph}).status_code for _ in range(4)]
        assert codes == [200, 200, 200, 429], codes


# ---------- R9/R5 multi booking + deposit ----------
class TestMultiBooking:
    def test_slots_multi_and_book_multi(self, H):
        r = requests.post(f"{API}/public/salon/{SLUG}/slots-multi", json={"branch_id": ZONA10, "date": DATE,
                          "lines": [{"service_id": CORTE, "stylist_id": CARLA}, {"service_id": BALAYAGE, "stylist_id": ""}]})
        assert r.status_code == 200, r.text
        opts = r.json()["options"]
        assert opts, "no multi options"
        o = opts[-1]
        assert len(o["plan"]) == 2 and o["plan"][0]["stylist_id"] == CARLA
        assert o["plan"][1]["time"] >= o["plan"][0]["end_time"]
        b = requests.post(f"{API}/public/salon/{SLUG}/book-multi", json={"branch_id": ZONA10, "date": DATE, "plan": o["plan"],
                          "phone": TEST_PHONE, "name": f"TEST_Cliente {RUN}"})
        assert b.status_code == 200, b.text
        d = b.json()
        CREATED["appts"] += [a["id"] for a in d["appointments"]]
        assert len(d["appointments"]) == 2
        bal = [a for a in d["appointments"] if a["service_id"] == BALAYAGE][0]
        assert bal["deposit_required"] == 360.0 and bal["status"] == "pending" and bal["deposit_status"] == "pending"
        assert d["deposit_total"] == 360.0
        ag = requests.get(f"{API}/appointments", params={"date": DATE}, headers=H["admin"]).json()
        ids = {a["id"] for a in ag}
        assert all(a["id"] in ids for a in d["appointments"])
        pytest.bal = bal
        pytest.corte = [a for a in d["appointments"] if a["service_id"] == CORTE][0]

    def test_deposit_received_confirms(self, H):
        r = requests.post(f"{API}/appointments/{pytest.bal['id']}/deposit", json={}, headers=H["rec"])
        assert r.status_code == 200
        a = mdb.appointments.find_one({"id": pytest.bal["id"]})
        assert a["status"] == "confirmed" and a["deposit_paid"] == 360.0

    def test_ics(self):
        a = pytest.corte
        r = requests.get(f"{API}/public/salon/{SLUG}/ics/{a['id']}", params={"t": a["review_token"]})
        assert r.status_code == 200 and "BEGIN:VCALENDAR" in r.text and "text/calendar" in r.headers["content-type"]
        assert requests.get(f"{API}/public/salon/{SLUG}/ics/{a['id']}", params={"t": "x"}).status_code == 404


# ---------- R3/R11/R16 checkout, cash, commissions, reviews ----------
class TestCheckout:
    def test_validation(self, H):
        a = pytest.corte
        u = f"{API}/appointments/{a['id']}/checkout"
        assert requests.post(u, json={"payments": [{"method": "cash", "amount": 100}]}, headers=H["rec"]).status_code == 400
        assert requests.post(u, json={"discount": 20, "payments": [{"method": "cash", "amount": 130}]}, headers=H["rec"]).status_code == 400

    def test_mixed_ok(self, H):
        a = pytest.corte
        r = requests.post(f"{API}/appointments/{a['id']}/checkout", json={"discount": 20, "discount_reason": "TEST_promo", "tip": 15,
                          "payments": [{"method": "cash", "amount": 100}, {"method": "card", "amount": 45}]}, headers=H["rec"])
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["total"] == 145 and s["net"] == 130 and s["tip"] == 15
        pytest.sale = s
        ap = mdb.appointments.find_one({"id": a["id"]})
        assert ap["status"] == "completed" and ap["sale_id"] == s["id"]
        print("commission", s["commission"])

    def test_deposit_applied_checkout(self, H):
        a = pytest.bal  # 1200 - 360 deposit = 840
        r = requests.post(f"{API}/appointments/{a['id']}/checkout", json={"payments": [{"method": "transfer", "amount": 840}]}, headers=H["admin"])
        assert r.status_code == 200, r.text
        assert r.json()["deposit_applied"] == 360

    def test_cash_report(self, H):
        d = requests.get(f"{API}/cash", headers=H["admin"]).json()
        ids = [s["id"] for s in d["sales"]]
        assert pytest.sale["id"] in ids
        assert d["by_method"].get("card", 0) >= 45 and d["by_method"].get("transfer", 0) >= 840
        x = requests.get(f"{API}/cash", params={"format": "xlsx"}, headers=H["admin"])
        assert x.status_code == 200 and "spreadsheet" in x.headers["content-type"] and x.content[:2] == b"PK"

    def test_completed_cannot_cancel_by_reception(self, H):
        r = requests.post(f"{API}/appointments/{pytest.corte['id']}/status", json={"status": "cancelled", "reason": "x"}, headers=H["rec"])
        assert r.status_code in (400, 409), r.status_code

    def test_review_flow(self, H):
        tok = pytest.corte["review_token"]
        msg = mdb.wa_messages.find_one({"company_id": CID, "phone": TEST_PHONE, "kind": "review"})
        assert msg and f"/b/{SLUG}/resena/" in msg["text"]
        assert requests.get(f"{API}/public/salon/{SLUG}/review/{tok}").json()["reviewed"] is False
        assert requests.post(f"{API}/public/salon/{SLUG}/review/{tok}", json={"rating": 6}).status_code == 400
        r = requests.post(f"{API}/public/salon/{SLUG}/review/{tok}", json={"rating": 2, "comment": "TEST_malo"})
        assert r.status_code == 200
        assert requests.post(f"{API}/public/salon/{SLUG}/review/{tok}", json={"rating": 5}).status_code == 400
        assert mdb.notifications.find_one({"company_id": CID, "text": {"$regex": "TEST_malo"}})
        rev = [x for x in requests.get(f"{API}/reviews", headers=H["admin"]).json() if x["comment"] == "TEST_malo"][0]
        assert requests.put(f"{API}/reviews/{rev['id']}", json={"hidden": True}, headers=H["rec"]).status_code == 403
        assert requests.put(f"{API}/reviews/{rev['id']}", json={"hidden": True}, headers=H["admin"]).status_code == 200
        pub = requests.get(f"{API}/public/salon/{SLUG}").json()
        assert all(x["comment"] != "TEST_malo" for x in pub["reviews"])

    def test_commissions(self, H):
        r = requests.get(f"{API}/commissions", params={"start": DATE, "end": DATE}, headers=H["admin"])
        assert r.status_code == 200 and any(x["stylist"] == "Diego Ruiz" for x in r.json())
        x = requests.get(f"{API}/commissions", params={"start": DATE, "end": DATE, "format": "xlsx"}, headers=H["admin"])
        assert x.content[:2] == b"PK"
        assert requests.get(f"{API}/commissions", params={"start": DATE, "end": DATE}, headers=H["rec"]).status_code == 403

    def test_void(self, H):
        sid = pytest.sale["id"]
        assert requests.post(f"{API}/sales/{sid}/void", json={"reason": "x"}, headers=H["rec"]).status_code == 403
        assert requests.post(f"{API}/sales/{sid}/void", json={"reason": "TEST"}, headers=H["admin"]).status_code == 200
        assert mdb.sales.find_one({"id": sid})["voided"] is True
        assert mdb.appointments.find_one({"id": pytest.corte["id"]})["status"] == "confirmed"

    def test_admin_reopen_completed(self, H):
        bal = pytest.bal["id"]
        r = requests.post(f"{API}/appointments/{bal}/status", json={"status": "confirmed", "reason": "corregir"}, headers=H["admin"])
        assert r.status_code == 200


# ---------- R5 late cancel from portal ----------
class TestLateCancel:
    def test_portal_late_cancel(self):
        tomorrow = "2026-10-16"
        sl = requests.get(f"{API}/public/salon/{SLUG}/slots", params={"branch_id": ZONA10, "service_id": CORTE, "date": tomorrow}).json()["slots"]
        assert sl
        b = requests.post(f"{API}/public/salon/{SLUG}/book", json={"branch_id": ZONA10, "service_id": CORTE, "date": tomorrow,
                          "time": sl[0]["time"], "phone": TEST_PHONE, "name": f"TEST_Cliente {RUN}"})
        assert b.status_code == 200, b.text
        aid = b.json()["id"]; CREATED["appts"].append(aid)
        mdb.otp_codes.delete_many({"phone": TEST_PHONE})
        requests.post(f"{API}/public/salon/{SLUG}/otp", json={"phone": TEST_PHONE})
        tok = requests.post(f"{API}/public/salon/{SLUG}/otp/verify", json={"phone": TEST_PHONE, "code": otp_code(TEST_PHONE)}).json()["token"]
        acc = requests.get(f"{API}/public/salon/{SLUG}/account", headers={"X-Client-Token": tok}).json()
        assert any(a["id"] == aid for a in acc["upcoming"])
        r = requests.post(f"{API}/public/salon/{SLUG}/appointments/{aid}", json={"action": "cancel", "reason": "TEST"}, headers={"X-Client-Token": tok})
        assert r.status_code == 200
        assert mdb.appointments.find_one({"id": aid}).get("late_cancel") is True
        d = requests.post(f"{API}/public/salon/{SLUG}/account/delete-request", headers={"X-Client-Token": tok})
        assert d.status_code == 200


# ---------- R5 release_unpaid ----------
def test_release_unpaid():
    sl = requests.get(f"{API}/public/salon/{SLUG}/slots", params={"branch_id": ZONA10, "service_id": BALAYAGE, "date": "2026-10-20"}).json()["slots"]
    b = requests.post(f"{API}/public/salon/{SLUG}/book", json={"branch_id": ZONA10, "service_id": BALAYAGE, "date": "2026-10-20",
                      "time": sl[0]["time"], "phone": TEST_PHONE, "name": f"TEST_Cliente {RUN}"}).json()
    CREATED["appts"].append(b["id"])
    assert b["status"] == "pending" and b["deposit_required"] == 360
    mdb.appointments.update_one({"id": b["id"]}, {"$set": {"deposit_due": "2026-01-01 00:00"}})
    import sys
    sys.path.insert(0, "/app/backend")
    os.environ.update({k: v for k, v in BENV.items() if v})
    import engine
    asyncio.get_event_loop().run_until_complete(engine.release_unpaid()) if False else asyncio.run(engine.release_unpaid())
    a = mdb.appointments.find_one({"id": b["id"]})
    assert a["status"] == "cancelled" and a["deposit_status"] == "expired"


# ---------- R17 inventory ----------
class TestInventory:
    def test_product_flow(self, H):
        r = requests.post(f"{API}/products", json={"name": f"TEST_Shampoo {RUN}", "price": 50, "cost": 20, "stock": 3, "min_stock": 2}, headers=H["admin"])
        assert r.status_code in (200, 201), r.text
        pid = r.json()["id"]; CREATED["products"].append(pid)
        assert requests.post(f"{API}/products/sale", json={"items": [{"product_id": pid, "qty": 5}], "payments": [{"method": "cash", "amount": 250}]}, headers=H["rec"]).status_code == 400
        s = requests.post(f"{API}/products/sale", json={"items": [{"product_id": pid, "qty": 2}], "branch_id": ZONA10,
                          "payments": [{"method": "cash", "amount": 100}]}, headers=H["rec"])
        assert s.status_code == 200, s.text
        assert mdb.products.find_one({"id": pid})["stock"] == 1
        al = requests.get(f"{API}/dashboard/alerts", headers=H["admin"]).json()
        assert any(p["id"] == pid for p in al["low_stock"])
        assert requests.post(f"{API}/products/{pid}/adjust", json={"qty": 5}, headers=H["admin"]).status_code == 400
        assert requests.post(f"{API}/products/{pid}/adjust", json={"qty": 5, "reason": "TEST"}, headers=H["admin"]).status_code == 200
        assert mdb.products.find_one({"id": pid})["stock"] == 6
        assert s.json()["id"] in [x["id"] for x in requests.get(f"{API}/cash", headers=H["admin"]).json()["sales"]]
        assert requests.delete(f"{API}/products/{pid}", headers=H["admin"]).status_code in (200, 204)


# ---------- R12 client lookup / photo consent ----------
class TestClient:
    def test_lookup_and_consent(self, H):
        cl = mdb.clients.find_one({"company_id": CID, "phone": TEST_PHONE})
        assert cl
        r = requests.put(f"{API}/clients/{cl['id']}", json={"photo_consent": False, "notes": {"allergies": "TEST_amoniaco"}}, headers=H["admin"])
        assert r.status_code == 200, r.text
        lk = requests.get(f"{API}/clients/lookup", params={"phone": TEST_PHONE}, headers=H["rec"]).json()
        print("lookup", lk)
        assert lk["exists"] is True
        up = requests.post(f"{API}/clients/{cl['id']}/files", files={"file": ("a.png", b"\x89PNG....", "image/png")}, data={"kind": "antes"}, headers=H["admin"])
        assert up.status_code == 400, up.status_code

    def test_media_upload(self, H):
        r = requests.post(f"{API}/company/media", files={"file": ("a.png", b"\x89PNG\r\n", "image/png")}, headers=H["admin"])
        assert r.status_code == 200
        CREATED["media"].append(r.json()["id"])
        assert requests.get(f"{BASE_URL}{r.json()['url']}").status_code == 200
        assert requests.post(f"{API}/company/media", files={"file": ("a.txt", b"hi", "text/plain")}, headers=H["admin"]).status_code == 400


# ---------- R8 signup / slug / billing ----------
class TestSignup:
    def test_slug_check(self):
        d = requests.get(f"{API}/public/slug-check", params={"slug": "bellavida"}).json()
        assert d["available"] is False and len(d["suggestions"]) > 0

    def test_signup_minimal_and_activate(self):
        r = requests.post(f"{API}/signup", json={"company_name": f"TEST_Salon {RUN}", "email": f"test_{RUN}@example.com",
                          "password": "Test2026!", "whatsapp_number": "+50251112222"})
        assert r.status_code == 200, r.text
        tok = {"Authorization": f"Bearer {r.json()['token']}"}
        me = requests.get(f"{API}/auth/me", headers=tok).json()
        cid = r.json()["user"]["company_id"]; CREATED["companies"].append(cid)
        co = mdb.companies.find_one({"id": cid})
        assert co["status"] == "trial", co["status"]
        tpl = requests.get(f"{API}/service-templates", headers=tok).json()
        assert requests.post(f"{API}/service-templates", json={"items": tpl[:2]}, headers=tok).json()["created"] == 2
        plans = requests.get(f"{API}/public/plans").json()["plans"]
        q = requests.post(f"{API}/billing/quote", json={"plan_id": plans[0]["id"]}, headers=tok).json()
        assert q["total"] == round(q["subtotal"] + q["tax"], 2)
        card = requests.post(f"{API}/gateway/tokenize", json={"number": "4111111111111111"}).json()
        a = requests.post(f"{API}/billing/activate", json={"plan_id": plans[0]["id"], "nit": "CF", "card": card}, headers=tok)
        assert a.status_code == 200, a.text
        print("me", me.get("email"), "status after", mdb.companies.find_one({"id": cid})["status"])


# ---------- R10 reminder template + email fallback ----------
def test_reminder_email_fallback(H):
    ph = "+5024" + str(uuid.uuid4().int)[:7]; CREATED["phones"].append(ph)
    sl = requests.get(f"{API}/public/salon/{SLUG}/slots", params={"branch_id": ZONA10, "service_id": CORTE, "date": "2026-10-16"}).json()["slots"]
    a = requests.post(f"{API}/appointments", json={"branch_id": ZONA10, "service_id": CORTE, "date": "2026-10-16", "time": sl[0]["time"],
                      "phone": ph, "name": f"TEST_Remind {RUN}"}, headers=H["admin"])
    assert a.status_code == 200, a.text
    CREATED["appts"].append(a.json()["id"])
    cl = mdb.clients.find_one({"company_id": CID, "phone": ph})
    assert requests.put(f"{API}/clients/{cl['id']}", json={"no_whatsapp": True, "email": f"test_{RUN}@example.com"}, headers=H["admin"]).status_code == 200
    requests.post(f"{API}/reminders/run", headers=H["admin"])
    em = mdb.email_outbox.find_one({"company_id": CID, "to": f"test_{RUN}@example.com"})
    assert em, "no email fallback reminder"
    print("email body:", em["body"])
    assert "Av. La Reforma" in em["body"] and "/b/bellavida" in em["body"]
    assert not mdb.wa_messages.find_one({"phone": ph, "kind": "reminder"})
    mdb.email_outbox.delete_many({"to": f"test_{RUN}@example.com"})
