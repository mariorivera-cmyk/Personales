# Iteration 18: service templates prep_minutes, coupon uses only after success, deposit excess w/ package, consume ordering, partial package PUT
import os, pytest, requests
from datetime import datetime, timedelta
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
CID = db.companies.find_one({"slug": "bellavida"})["id"]
BRANCH = "9c211150faac"
TRAT = "81a40e910fdd"   # 180
CORTE = "17f399d32a39"  # Mascarilla 120 (any stylist)
CARLA = "a14fc0cc74ec"
PHONE = "+50255018801"


def login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


OWNER = login("admin@bellavida.com", "Demo2026!")
RECEP = login("recepcion@bellavida.com", "Demo2026!")


def future(days):
    d = datetime.now() + timedelta(days=days)
    while d.weekday() == 6:
        d += timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def make_appt(service, days=3, deposit=0):
    for t in ("09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00"):
        for d in range(days, days + 15):
            r = requests.post(f"{API}/appointments", headers=OWNER, json={"branch_id": BRANCH, "service_id": service, "date": future(d),
                                                                         "time": t, "phone": PHONE, "name": "TEST_It18 Client", "stylist_id": CARLA})
            if r.status_code == 200:
                a = r.json()
                past = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                st = {"date": past, "status": "confirmed"}
                if deposit:
                    st.update(deposit_required=deposit, deposit_paid=deposit, deposit_status="received")
                db.appointments.update_one({"id": a["id"]}, {"$set": st})
                return {**a, **st}
    pytest.fail("could not book")


@pytest.fixture(scope="module")
def ctx():
    r = requests.post(f"{API}/clients", headers=OWNER, json={"phone": PHONE, "name": "TEST_It18 Client"})
    cl = r.json()
    cl = cl.get("client", cl)
    bv = db.loyalty_coupons.find_one({"company_id": CID, "code": "BIENVENIDA10"})
    st = {"client": cl, "bv_uses": bv.get("uses") if bv else None, "bv_has": bv is not None and "uses" in bv}
    yield st
    pk_ids = [p["id"] for p in db.packages.find({"company_id": CID, "name": {"$regex": "^TEST_It18"}})]
    cps = list(db.client_packages.find({"company_id": CID, "client_phone": PHONE}))
    db.sales.delete_many({"id": {"$in": [c["sale_id"] for c in cps]}})
    db.client_packages.delete_many({"company_id": CID, "client_phone": PHONE})
    db.packages.delete_many({"id": {"$in": pk_ids}})
    aids = [a["id"] for a in db.appointments.find({"company_id": CID, "client_phone": PHONE})]
    db.sales.delete_many({"appointment_id": {"$in": aids}})
    db.appointments.delete_many({"id": {"$in": aids}})
    db.clients.delete_many({"company_id": CID, "phone": PHONE})
    db.wa_messages.delete_many({"phone": PHONE})
    db.notifications.delete_many({"company_id": CID, "text": {"$regex": "TEST_It18"}})
    db.services.delete_many({"company_id": CID, "name": {"$regex": "^TEST_It18"}})
    if st["bv_has"]:
        db.loyalty_coupons.update_one({"code": "BIENVENIDA10", "company_id": CID}, {"$set": {"uses": st["bv_uses"]}})
    else:
        db.loyalty_coupons.update_one({"code": "BIENVENIDA10", "company_id": CID}, {"$unset": {"uses": ""}})


def uses():
    return (db.loyalty_coupons.find_one({"company_id": CID, "code": "BIENVENIDA10"}) or {}).get("uses", 0)


class TestTemplates:
    def test_templates_have_prep(self, ctx):
        r = requests.get(f"{API}/service-templates", headers=OWNER)
        assert r.status_code == 200 and r.json() and all(t["prep_minutes"] == 0 for t in r.json())
        assert requests.get(f"{API}/service-templates", headers=RECEP).status_code == 403

    def test_add_templates_prep(self, ctx):
        r = requests.post(f"{API}/service-templates", headers=OWNER, json={"items": [
            {"name": "TEST_It18 Svc A", "category": "TEST_It18Cat", "duration": 45, "price": 99, "prep_minutes": 15},
            {"name": "TEST_It18 Svc B", "category": "TEST_It18Cat", "duration": 30, "price": 50, "prep_minutes": -5},
            {"name": "TEST_It18 Svc C", "category": "TEST_It18Cat", "duration": 30, "price": 50}]})
        assert r.status_code == 200 and r.json()["created"] == 3
        svcs = {s["name"]: s for s in requests.get(f"{API}/services", headers=OWNER).json() if s["name"].startswith("TEST_It18")}
        assert svcs["TEST_It18 Svc A"]["prep_minutes"] == 15 and svcs["TEST_It18 Svc A"]["duration"] == 45
        assert svcs["TEST_It18 Svc B"]["prep_minutes"] == 0 and svcs["TEST_It18 Svc C"]["prep_minutes"] == 0
        db.service_categories.delete_many({"company_id": CID, "name": "TEST_It18Cat"})


class TestCoupon:
    def test_failed_checkout_no_increment(self, ctx):
        a = make_appt(TRAT, 3)
        ctx["a1"] = a
        u0 = uses()
        r = requests.post(f"{API}/appointments/{a['id']}/checkout", headers=RECEP, json={"coupon_code": "bienvenida10", "payments": [{"method": "cash", "amount": 100}]})
        assert r.status_code == 400
        assert uses() == u0
        r = requests.post(f"{API}/appointments/{a['id']}/checkout", headers=RECEP, json={"coupon_code": "bienvenida10", "payments": [{"method": "cash", "amount": 162}]})
        assert r.status_code == 200 and r.json()["total"] == 162.0
        assert uses() == u0 + 1


class TestPackageDeposit:
    def test_create_package_and_sell(self, ctx):
        r = requests.post(f"{API}/packages", headers=OWNER, json={"name": "TEST_It18 Pack", "items": [{"service_id": TRAT, "qty": 3}], "price": 450, "validity_days": 30, "active": True})
        assert r.status_code == 200, r.text
        ctx["pkg"] = r.json()
        r = requests.post(f"{API}/client-packages", headers=OWNER, json={"client_id": ctx["client"]["id"], "package_id": ctx["pkg"]["id"],
                                                                        "branch_id": BRANCH, "payments": [{"method": "cash", "amount": 450}]})
        assert r.status_code == 200, r.text
        ctx["cp"] = r.json()

    def test_deposit_full_cover(self, ctx):
        a = make_appt(TRAT, 4, deposit=50)
        n0 = db.notifications.count_documents({"company_id": CID, "title": "Anticipo por devolver"})
        o = requests.get(f"{API}/appointments/{a['id']}/checkout-options", headers=RECEP).json()
        assert o["package_cover"] == 180.0
        r = requests.post(f"{API}/appointments/{a['id']}/checkout", headers=RECEP, json={"package_id": ctx["cp"]["id"], "tip": 10, "payments": [{"method": "cash", "amount": 10}]})
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["total"] == 10.0 and s["deposit_applied"] == 0 and s["deposit_excess"] == 50.0, s
        assert db.notifications.count_documents({"company_id": CID, "title": "Anticipo por devolver"}) == n0 + 1
        nt = db.notifications.find_one({"company_id": CID, "title": "Anticipo por devolver"}, sort=[("created_at", -1)])
        assert "Q50.00" in nt["text"] and "TEST_It18" in nt["text"]
        cp = db.client_packages.find_one({"id": ctx["cp"]["id"]})
        assert sum(i["used"] for i in cp["items"]) == 1
        ctx["s_dep"] = s

    def test_deposit_partial(self, ctx):
        # Mascarilla 120, deposit 50, manual discount 90 -> due 30, dep applied 30, excess 20
        a = make_appt(CORTE, 5, deposit=50)
        r = requests.post(f"{API}/appointments/{a['id']}/checkout", headers=RECEP, json={"discount": 90, "discount_reason": "TEST", "payments": []})
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["deposit_applied"] == 30.0 and s["deposit_excess"] == 20.0 and s["total"] == 0

    def test_deposit_normal_no_excess(self, ctx):
        a = make_appt(CORTE, 6, deposit=50)
        n0 = db.notifications.count_documents({"company_id": CID, "title": "Anticipo por devolver"})
        r = requests.post(f"{API}/appointments/{a['id']}/checkout", headers=RECEP, json={"payments": [{"method": "cash", "amount": 70}]})
        assert r.status_code == 200, r.text
        assert r.json()["deposit_applied"] == 50.0 and r.json()["deposit_excess"] == 0
        assert db.notifications.count_documents({"company_id": CID, "title": "Anticipo por devolver"}) == n0

    def test_failed_checkout_no_consume(self, ctx):
        a = make_appt(TRAT, 7)
        ctx["a7"] = a
        before = sum(i["used"] for i in db.client_packages.find_one({"id": ctx["cp"]["id"]})["items"])
        r = requests.post(f"{API}/appointments/{a['id']}/checkout", headers=RECEP, json={"package_id": ctx["cp"]["id"], "tip": 5, "payments": []})
        assert r.status_code == 400
        assert sum(i["used"] for i in db.client_packages.find_one({"id": ctx["cp"]["id"]})["items"]) == before
        assert db.appointments.find_one({"id": a["id"]})["status"] == "confirmed"

    def test_set_status_fail_restores(self, ctx):
        # force set_status failure: make appointment status invalid for completion after promos check? use 'no_show'
        a = ctx["a7"]
        db.appointments.update_one({"id": a["id"]}, {"$set": {"status": "no_show"}})
        before = sum(i["used"] for i in db.client_packages.find_one({"id": ctx["cp"]["id"]})["items"])
        r = requests.post(f"{API}/appointments/{a['id']}/checkout", headers=RECEP, json={"package_id": ctx["cp"]["id"], "payments": []})
        after = db.client_packages.find_one({"id": ctx["cp"]["id"]})
        print("no_show checkout:", r.status_code, r.text[:200])
        if r.status_code != 200:
            assert sum(i["used"] for i in after["items"]) == before
            assert not any(u.get("appointment_id") == a["id"] for u in after.get("uses", []))
        db.appointments.update_one({"id": a["id"]}, {"$set": {"status": "confirmed"}})

    def test_checkout_once_and_void_restores(self, ctx):
        a = make_appt(TRAT, 8)
        before = sum(i["used"] for i in db.client_packages.find_one({"id": ctx["cp"]["id"]})["items"])
        r = requests.post(f"{API}/appointments/{a['id']}/checkout", headers=RECEP, json={"package_id": ctx["cp"]["id"], "payments": []})
        assert r.status_code == 200, r.text
        assert sum(i["used"] for i in db.client_packages.find_one({"id": ctx["cp"]["id"]})["items"]) == before + 1
        v = requests.post(f"{API}/sales/{r.json()['id']}/void", headers=OWNER, json={"reason": "TEST"})
        assert v.status_code == 200
        cp = db.client_packages.find_one({"id": ctx["cp"]["id"]})
        assert sum(i["used"] for i in cp["items"]) == before
        assert not any(u.get("appointment_id") == a["id"] for u in cp.get("uses", []))


class TestPartialPut:
    def test_partial_active_false(self, ctx):
        pid = ctx["pkg"]["id"]
        r = requests.put(f"{API}/packages/{pid}", headers=OWNER, json={"active": False})
        assert r.status_code == 200, r.text
        p = db.packages.find_one({"id": pid})
        assert p["active"] is False and p["price"] == 450.0 and len(p["items"]) == 1

    @pytest.mark.parametrize("bad", [{"price": 0}, {"price": -5}, {"validity_days": 0}, {"validity_days": -1}])
    def test_partial_bad(self, ctx, bad):
        r = requests.put(f"{API}/packages/{ctx['pkg']['id']}", headers=OWNER, json=bad)
        assert r.status_code == 400, r.text

    def test_full_update_validation(self, ctx):
        pid = ctx["pkg"]["id"]
        full = {"name": "TEST_It18 Pack", "items": [{"service_id": TRAT, "qty": 3}], "price": 450, "validity_days": 30, "active": True}
        assert requests.put(f"{API}/packages/{pid}", headers=OWNER, json={**full, "items": []}).status_code == 400
        assert requests.put(f"{API}/packages/{pid}", headers=OWNER, json={**full, "price": 0}).status_code == 400
        r = requests.put(f"{API}/packages/{pid}", headers=OWNER, json={**full, "price": 500})
        assert r.status_code == 200 and r.json()["price"] == 500.0

    def test_partial_string_price(self, ctx):
        r = requests.put(f"{API}/packages/{ctx['pkg']['id']}", headers=OWNER, json={"price": "abc"})
        print("string price:", r.status_code, r.text[:120])
        assert r.status_code in (400, 422), r.text
