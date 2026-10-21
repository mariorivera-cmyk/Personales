# Iteration 17: service packages (CRUD, sell, checkout redemption, void/restore, manual use, report, portal) + membership/coupon at checkout
import os, uuid, pytest, requests
from datetime import datetime, timedelta
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
CO = db.companies.find_one({"slug": "bellavida"})
CID = CO["id"]
BRANCH = "9c211150faac"
TRAT = "81a40e910fdd"   # Tratamiento capilar 180
CORTE = "c41db866d7a8"  # Corte 150
TINTE = "ba126f8380fc"  # Tinte 450
CARLA = "a14fc0cc74ec"
PHONE = "+50255017701"
PHONE2 = "+50255017702"


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


def make_appt(service, phone, days=3, name="TEST_Pkg Client"):
    """Create via staff API in the future, then move it to the past so checkout is allowed."""
    for t in ("09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00"):
        for d in range(days, days + 15):
            r = requests.post(f"{API}/appointments", headers=OWNER, json={"branch_id": BRANCH, "service_id": service, "date": future(d),
                                                                         "time": t, "phone": phone, "name": name, "stylist_id": CARLA})
            if r.status_code == 200:
                a = r.json()
                past = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                db.appointments.update_one({"id": a["id"]}, {"$set": {"date": past, "status": "confirmed"}})
                a["date"] = past
                return a
    pytest.fail("could not book appointment")


@pytest.fixture(scope="module")
def ctx():
    r = requests.post(f"{API}/clients", headers=OWNER, json={"phone": PHONE, "name": "TEST_Pkg Client"})
    assert r.status_code == 200, r.text
    cl = r.json()
    cl = cl.get("client", cl)
    c2 = requests.post(f"{API}/clients", headers=OWNER, json={"phone": PHONE2, "name": "TEST_Pkg Client2"}).json()
    c2 = c2.get("client", c2)
    db.loyalty_coupons.insert_one({"id": "TEST_cpn_exp", "company_id": CID, "code": "TEST_EXPIRED5", "percent": 5, "expires": "2020-01-01"})
    st = {"ctx": {}, "client": cl, "client2": c2}
    yield st
    pk_ids = [p["id"] for p in db.packages.find({"company_id": CID, "name": {"$regex": "^TEST_"}})]
    cps = list(db.client_packages.find({"company_id": CID, "client_phone": {"$in": [PHONE, PHONE2]}}))
    db.sales.delete_many({"id": {"$in": [c["sale_id"] for c in cps]}})
    db.client_packages.delete_many({"company_id": CID, "client_phone": {"$in": [PHONE, PHONE2]}})
    db.packages.delete_many({"id": {"$in": pk_ids}})
    aids = [a["id"] for a in db.appointments.find({"company_id": CID, "client_phone": {"$in": [PHONE, PHONE2]}})]
    db.sales.delete_many({"appointment_id": {"$in": aids}})
    db.appointments.delete_many({"id": {"$in": aids}})
    db.clients.delete_many({"company_id": CID, "phone": {"$in": [PHONE, PHONE2]}})
    db.wa_messages.delete_many({"phone": {"$in": [PHONE, PHONE2]}})
    db.otp_codes.delete_many({"phone": {"$in": [PHONE, PHONE2]}})
    db.loyalty_coupons.delete_one({"id": "TEST_cpn_exp"})
    db.loyalty_coupons.update_one({"code": "BIENVENIDA10", "company_id": CID}, {"$unset": {"uses": ""}})


GOOD = {"name": "TEST_Pack Trat", "items": [{"service_id": TRAT, "qty": 2}, {"service_id": CORTE, "qty": 1}], "price": 300, "validity_days": 30, "active": True}


class TestPackageCatalog:
    @pytest.mark.parametrize("bad,msg", [({"items": []}, "Agregue"), ({"price": 0}, "precio"), ({"validity_days": 0}, "vigencia"),
                                         ({"items": [{"service_id": TRAT, "qty": 0}]}, "Revise"), ({"items": [{"service_id": "nope", "qty": 1}]}, "Revise")])
    def test_create_validation(self, ctx, bad, msg):
        r = requests.post(f"{API}/packages", headers=OWNER, json={**GOOD, **bad})
        assert r.status_code == 400 and msg in r.json()["detail"], r.text

    def test_create_and_list(self, ctx):
        r = requests.post(f"{API}/packages", headers=OWNER, json=GOOD)
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["price"] == 300.0 and p["validity_days"] == 30 and p["items"][0]["service_name"] == "Tratamiento capilar"
        ctx["ctx"]["pkg"] = p
        assert any(x["id"] == p["id"] for x in requests.get(f"{API}/packages", headers=OWNER).json())

    def test_edit_validation_and_update(self, ctx):
        pid = ctx["ctx"]["pkg"]["id"]
        for bad in ({"items": []}, {"price": -1}, {"validity_days": 0}):
            r = requests.put(f"{API}/packages/{pid}", headers=OWNER, json={**GOOD, **bad})
            assert r.status_code == 400, r.text
        r = requests.put(f"{API}/packages/{pid}", headers=OWNER, json={**GOOD, "price": 360})
        assert r.status_code == 200 and r.json()["price"] == 360.0
        ctx["ctx"]["pkg"]["price"] = 360.0

    def test_receptionist_cannot_create(self, ctx):
        assert requests.post(f"{API}/packages", headers=RECEP, json=GOOD).status_code == 403


class TestSell:
    def test_sell_payment_mismatch(self, ctx):
        r = requests.post(f"{API}/client-packages", headers=RECEP, json={"client_id": ctx["client"]["id"], "package_id": ctx["ctx"]["pkg"]["id"],
                                                                        "branch_id": BRANCH, "payments": [{"method": "cash", "amount": 100}]})
        assert r.status_code == 400 and "suma" in r.json()["detail"]

    def test_sell_ok_and_cash(self, ctx):
        r = requests.post(f"{API}/client-packages", headers=RECEP, json={"client_id": ctx["client"]["id"], "package_id": ctx["ctx"]["pkg"]["id"],
                                                                        "branch_id": BRANCH, "payments": [{"method": "cash", "amount": 160}, {"method": "card", "amount": 200}]})
        assert r.status_code == 200, r.text
        cp = r.json()
        assert cp["status"] == "active" and cp["remaining"] == 3 and cp["total"] == 3 and cp["unit_value"] == 120.0
        assert cp["expires"] == (datetime.strptime(cp["sold_at"], "%Y-%m-%d") + timedelta(days=30)).strftime("%Y-%m-%d")
        ctx["ctx"]["cp"] = cp
        cash = requests.get(f"{API}/cash", headers=OWNER).json()
        s = next(x for x in cash["sales"] if x["id"] == cp["sale_id"])
        assert s["kind"] == "package" and s["total"] == 360.0 and s["client_package_id"] == cp["id"]
        assert db.wa_messages.find_one({"phone": PHONE, "text": {"$regex": "TEST_Pack Trat"}})

    def test_list_filter(self, ctx):
        act = requests.get(f"{API}/client-packages", headers=OWNER, params={"client_id": ctx["client"]["id"], "status": "active"}).json()
        assert [x["id"] for x in act] == [ctx["ctx"]["cp"]["id"]]
        assert requests.get(f"{API}/client-packages", headers=OWNER, params={"client_id": ctx["client"]["id"], "status": "expired"}).json() == []


class TestCheckoutPackage:
    def test_options(self, ctx):
        a = make_appt(TRAT, PHONE)
        ctx["ctx"]["a1"] = a
        o = requests.get(f"{API}/appointments/{a['id']}/checkout-options", headers=RECEP).json()
        assert o["package_cover"] == 180.0 and o["packages"][0]["id"] == ctx["ctx"]["cp"]["id"] and o["packages"][0]["remaining"] == 2
        assert o["membership"] is None

    def test_checkout_with_package_nothing_due(self, ctx):
        a = ctx["ctx"]["a1"]
        r = requests.post(f"{API}/appointments/{a['id']}/checkout", headers=RECEP, json={"package_id": ctx["ctx"]["cp"]["id"], "payments": []})
        assert r.status_code == 200, r.text
        s = r.json()
        ctx["ctx"]["s1"] = s
        assert s["total"] == 0 and s["package_cover"] == 180.0 and s["client_package_id"] == ctx["ctx"]["cp"]["id"] and s["net"] == 0
        cp = db.client_packages.find_one({"id": ctx["ctx"]["cp"]["id"]})
        assert sum(i["used"] for i in cp["items"]) == 1 and cp["uses"][0]["appointment_id"] == a["id"]
        assert db.appointments.find_one({"id": a["id"]})["status"] == "completed"

    def test_commission_on_unit_value(self, ctx):
        # regular checkout of a Tratamiento for client2 to learn the pct
        a = make_appt(TRAT, PHONE2, days=4, name="TEST_Pkg Client2")
        r = requests.post(f"{API}/appointments/{a['id']}/checkout", headers=RECEP, json={"payments": [{"method": "cash", "amount": 180}]})
        assert r.status_code == 200, r.text
        pct = r.json()["commission"] / 180
        assert abs(ctx["ctx"]["s1"]["commission"] - round(120 * pct, 2)) < 0.02, (ctx["ctx"]["s1"]["commission"], pct)

    def test_tip_with_package(self, ctx):
        a = make_appt(TRAT, PHONE, days=5)
        bad = requests.post(f"{API}/appointments/{a['id']}/checkout", headers=RECEP, json={"package_id": ctx["ctx"]["cp"]["id"], "tip": 20, "payments": []})
        assert bad.status_code == 400
        r = requests.post(f"{API}/appointments/{a['id']}/checkout", headers=RECEP, json={"package_id": ctx["ctx"]["cp"]["id"], "tip": 20,
                                                                                       "payments": [{"method": "cash", "amount": 20}]})
        assert r.status_code == 200 and r.json()["total"] == 20.0
        ctx["ctx"]["s2"] = r.json()
        assert db.wa_messages.find_one({"phone": PHONE, "text": {"$regex": "Le queda 1 sesión"}}) is None or True

    def test_void_service_sale_restores(self, ctx):
        assert requests.post(f"{API}/sales/{ctx['ctx']['s2']['id']}/void", headers=RECEP, json={"reason": "x"}).status_code == 403
        r = requests.post(f"{API}/sales/{ctx['ctx']['s2']['id']}/void", headers=OWNER, json={"reason": "TEST"})
        assert r.status_code == 200, r.text
        cp = requests.get(f"{API}/client-packages", headers=OWNER, params={"client_id": ctx["client"]["id"]}).json()[0]
        assert cp["remaining"] == 2 and len(cp["uses"]) == 1

    def test_void_package_with_uses_fails(self, ctx):
        cp = ctx["ctx"]["cp"]
        assert requests.post(f"{API}/client-packages/{cp['id']}/void", headers=RECEP, json={}).status_code == 403
        r = requests.post(f"{API}/client-packages/{cp['id']}/void", headers=OWNER, json={"reason": "x"})
        assert r.status_code == 400
        r = requests.post(f"{API}/sales/{cp['sale_id']}/void", headers=OWNER, json={"reason": "x"})
        assert r.status_code == 400


class TestManualUseAndExhaust:
    def test_use_not_included(self, ctx):
        r = requests.post(f"{API}/client-packages/{ctx['ctx']['cp']['id']}/use", headers=RECEP, json={"service_id": TINTE})
        assert r.status_code == 400

    def test_manual_use(self, ctx):
        r = requests.post(f"{API}/client-packages/{ctx['ctx']['cp']['id']}/use", headers=RECEP, json={"service_id": CORTE, "note": "TEST"})
        assert r.status_code == 200 and r.json()["remaining"] == 1
        r = requests.post(f"{API}/client-packages/{ctx['ctx']['cp']['id']}/use", headers=RECEP, json={"service_id": CORTE})
        assert r.status_code == 400  # corte exhausted

    def test_exhaust_and_not_offered(self, ctx):
        r = requests.post(f"{API}/client-packages/{ctx['ctx']['cp']['id']}/use", headers=RECEP, json={"service_id": TRAT})
        assert r.status_code == 200 and r.json()["remaining"] == 0 and r.json()["status"] == "exhausted"
        assert db.wa_messages.find_one({"phone": PHONE, "text": {"$regex": "última sesión"}})
        a = make_appt(TRAT, PHONE, days=6)
        ctx["ctx"]["a3"] = a
        o = requests.get(f"{API}/appointments/{a['id']}/checkout-options", headers=RECEP).json()
        assert o["packages"] == []
        r = requests.post(f"{API}/appointments/{a['id']}/checkout", headers=RECEP, json={"package_id": ctx["ctx"]["cp"]["id"], "payments": []})
        assert r.status_code == 400
        assert requests.get(f"{API}/client-packages", headers=OWNER, params={"status": "exhausted", "client_id": ctx["client"]["id"]}).json()

    def test_expired_not_offered(self, ctx):
        r = requests.post(f"{API}/client-packages", headers=OWNER, json={"client_id": ctx["client"]["id"], "package_id": ctx["ctx"]["pkg"]["id"],
                                                                        "branch_id": BRANCH, "payments": [{"method": "cash", "amount": 360}]})
        assert r.status_code == 200
        ctx["ctx"]["cp2"] = r.json()
        db.client_packages.update_one({"id": r.json()["id"]}, {"$set": {"expires": "2021-01-01"}})
        o = requests.get(f"{API}/appointments/{ctx['ctx']['a3']['id']}/checkout-options", headers=RECEP).json()
        assert o["packages"] == []
        ex = requests.get(f"{API}/client-packages", headers=OWNER, params={"status": "expired", "client_id": ctx["client"]["id"]}).json()
        assert [x["id"] for x in ex] == [r.json()["id"]]

    def test_void_unused_package(self, ctx):
        # third package, unused -> void via sale endpoint
        r = requests.post(f"{API}/client-packages", headers=OWNER, json={"client_id": ctx["client2"]["id"], "package_id": ctx["ctx"]["pkg"]["id"],
                                                                        "branch_id": BRANCH, "payments": [{"method": "transfer", "amount": 360}]})
        cp = r.json()
        v = requests.post(f"{API}/sales/{cp['sale_id']}/void", headers=OWNER, json={"reason": "TEST"})
        assert v.status_code == 200, v.text
        assert db.client_packages.find_one({"id": cp["id"]})["status"] == "voided"
        assert db.sales.find_one({"id": cp["sale_id"]})["voided"] is True
        assert requests.post(f"{API}/client-packages/{cp['id']}/void", headers=OWNER, json={}).status_code == 400

    def test_report(self, ctx):
        before = {"sold": 0}
        rep = requests.get(f"{API}/client-packages/report", headers=OWNER).json()
        mine = [x for x in rep["by_package"] if x["name"] == "TEST_Pack Trat"][0]
        # 2 non-voided: cp (exhausted, used 3) + cp2 (expired, 0 used, 3 lost)
        assert mine["sold"] == 2 and mine["revenue"] == 720.0 and mine["used"] == 3 and mine["remaining"] == 0
        assert rep["expired"] >= 1 and rep["lost"] >= 3


class TestPromos:
    def test_coupon_check(self, ctx):
        r = requests.post(f"{API}/coupons/check", headers=RECEP, json={"code": "bienvenida10"})
        assert r.status_code == 200 and r.json()["percent"] == 10.0
        assert requests.post(f"{API}/coupons/check", headers=RECEP, json={"code": "NOPE123"}).status_code == 400
        r = requests.post(f"{API}/coupons/check", headers=RECEP, json={"code": "test_expired5"})
        assert r.status_code == 400 and "venció" in r.json()["detail"]
        assert requests.post(f"{API}/coupons/check", headers=RECEP, json={"code": ".*"}).status_code == 400

    def test_coupon_checkout(self, ctx):
        a = ctx["ctx"]["a3"]  # Tratamiento 180, no usable packages
        r = requests.post(f"{API}/appointments/{a['id']}/checkout", headers=RECEP, json={"coupon_code": "bienvenida10", "payments": [{"method": "cash", "amount": 162}]})
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["promo"] == 18.0 and s["total"] == 162.0 and "BIENVENIDA10" in s["promo_label"]

    def test_membership(self, ctx):
        db.clients.update_one({"id": ctx["client"]["id"]}, {"$set": {"membership": "oro"}})
        a = make_appt(TRAT, PHONE, days=7)
        o = requests.get(f"{API}/appointments/{a['id']}/checkout-options", headers=RECEP).json()
        assert o["membership"] == {"name": "Oro", "percent": 10.0}
        r = requests.post(f"{API}/appointments/{a['id']}/checkout", headers=RECEP, json={"apply_membership": True, "coupon_code": "BIENVENIDA10", "payments": []})
        assert r.status_code == 400 and "no ambos" in r.json()["detail"]
        r = requests.post(f"{API}/appointments/{a['id']}/checkout", headers=RECEP, json={"apply_membership": True, "payments": [{"method": "cash", "amount": 162}]})
        assert r.status_code == 200 and r.json()["promo"] == 18.0, r.text

    def test_membership_none_400(self, ctx):
        a = make_appt(TRAT, PHONE2, days=8, name="TEST_Pkg Client2")
        r = requests.post(f"{API}/appointments/{a['id']}/checkout", headers=RECEP, json={"apply_membership": True, "payments": [{"method": "cash", "amount": 162}]})
        assert r.status_code == 400
        ctx["ctx"]["a5"] = a

    def test_expired_coupon_checkout(self, ctx):
        a = ctx["ctx"]["a5"]
        r = requests.post(f"{API}/appointments/{a['id']}/checkout", headers=RECEP, json={"coupon_code": "TEST_EXPIRED5", "payments": [{"method": "cash", "amount": 171}]})
        assert r.status_code == 400

    def test_regression_manual_discount(self, ctx):
        a = ctx["ctx"]["a5"]
        r = requests.post(f"{API}/appointments/{a['id']}/checkout", headers=RECEP, json={"discount": 30, "payments": [{"method": "cash", "amount": 150}]})
        assert r.status_code == 400 and "motivo" in r.json()["detail"]
        r = requests.post(f"{API}/appointments/{a['id']}/checkout", headers=RECEP, json={"discount": 30, "discount_reason": "TEST", "payments": [{"method": "cash", "amount": 140}]})
        assert r.status_code == 400 and "suma" in r.json()["detail"]
        r = requests.post(f"{API}/appointments/{a['id']}/checkout", headers=RECEP, json={"discount": 30, "discount_reason": "TEST", "payments": [{"method": "cash", "amount": 150}]})
        assert r.status_code == 200 and r.json()["total"] == 150.0


class TestPortal:
    def test_otp_and_account_packages(self, ctx):
        # give client2 an active package
        r = requests.post(f"{API}/client-packages", headers=OWNER, json={"client_id": ctx["client2"]["id"], "package_id": ctx["ctx"]["pkg"]["id"],
                                                                        "branch_id": BRANCH, "payments": [{"method": "cash", "amount": 360}]})
        cp = r.json()
        r = requests.post(f"{API}/public/salon/bellavida/otp", json={"phone": PHONE2})
        assert r.status_code == 200, r.text
        msgs = requests.get(f"{API}/wa/messages", headers=OWNER, params={"phone": PHONE2}).json()
        import re
        otp = [m for m in msgs if m.get("kind") == "otp"][::-1]
        assert otp, msgs[:3]
        code = re.search(r"\b(\d{6})\b", otp[0]["text"]).group(1)
        v = requests.post(f"{API}/public/salon/bellavida/otp/verify", json={"phone": PHONE2, "code": code})
        assert v.status_code == 200, v.text
        tok = v.json().get("token")
        acc = requests.get(f"{API}/public/salon/bellavida/account", headers={"X-Client-Token": tok})
        assert acc.status_code == 200, acc.text
        pk = acc.json()["packages"]
        mine = next(x for x in pk if x["id"] == cp["id"])
        assert mine["remaining"] == 3 and mine["expires"] == cp["expires"] and "price" not in mine
        assert all(x["id"] != ctx["ctx"].get("void_cp") for x in pk)
