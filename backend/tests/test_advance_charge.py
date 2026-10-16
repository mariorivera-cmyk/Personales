# Advance charge (cobro adelantado) per company + removal of global billing run
import os
import uuid
import pytest
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pymongo import MongoClient


def _env(path, key):
    for line in open(path):
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"')


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _env("/app/frontend/.env", "REACT_APP_BACKEND_URL")).rstrip("/")
mdb = MongoClient(_env("/app/backend/.env", "MONGO_URL"))[_env("/app/backend/.env", "DB_NAME")]
TD = datetime.now(ZoneInfo("America/Guatemala"))
TODAY = TD.strftime("%Y-%m-%d")
D = lambda n: (TD + timedelta(days=n)).strftime("%Y-%m-%d")
PW = "TestPass2026!"
created = []


def login(e, p):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": e, "password": p})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def sa():
    return login("mario.rivera@gmail.com", "Admin2026!")


@pytest.fixture(scope="module", autouse=True)
def cleanup(sa):
    yield
    for cid in created:
        requests.delete(f"{BASE_URL}/api/admin/companies/{cid}", headers=sa, json={"confirm": "ELIMINAR"})
        mdb.invoices.delete_many({"company_id": cid})
        mdb.payments.delete_many({"company_id": cid})


def mk(sa, status="active", card="4242", cycle="monthly", **extra):
    plan = requests.get(f"{BASE_URL}/api/admin/plans", headers=sa).json()[0]["id"]
    s = uuid.uuid4().hex[:6]
    body = {"company_name": f"TEST_Adv {s}", "slug": f"test-adv-{s}", "email": f"test_adv_{s}@example.com", "password": PW,
            "plan_id": plan, "whatsapp_number": f"+50297{int(s, 16) % 1000000:06d}", "status": status, "billing_cycle": cycle}
    r = requests.post(f"{BASE_URL}/api/admin/companies", headers=sa, json=body)
    assert r.status_code == 200, r.text
    c = r.json()
    created.append(c["id"])
    upd = {**extra}
    if card:
        upd["card"] = {"last4": card, "brand": "Visa"}
    if upd:
        mdb.companies.update_one({"id": c["id"]}, {"$set": upd})
    c.update(upd)
    c["email"] = body["email"]
    return c


def url(cid):
    return f"{BASE_URL}/api/admin/companies/{cid}/advance-charge"


def co(cid):
    return mdb.companies.find_one({"id": cid}, {"_id": 0})


class TestRemovedRun:
    def test_billing_run_removed(self, sa):
        r = requests.post(f"{BASE_URL}/api/admin/billing/run", headers=sa)
        assert r.status_code in (404, 405), r.status_code


class TestPreview:
    def test_preview_active_future_nbd(self, sa):
        c = mk(sa, next_billing_date=D(10))
        r = requests.get(url(c["id"]), headers=sa)
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["period_from"] == D(10) and p["period_to"] == D(40)
        assert p["card_last4"] == "4242" and p["cycle"] == "monthly"
        assert round(p["subtotal"] + p["tax"], 2) == p["total"] and p["total"] > 0
        assert isinstance(p["items"], list) and p["items"]

    def test_preview_past_nbd_clamped_to_today(self, sa):
        c = mk(sa, next_billing_date=D(-5))
        p = requests.get(url(c["id"]), headers=sa).json()
        assert p["period_from"] == TODAY and p["period_to"] == D(30)

    def test_preview_trial_uses_trial_ends_annual(self, sa):
        c = mk(sa, status="trial", cycle="annual", trial_ends=D(7))
        p = requests.get(url(c["id"]), headers=sa).json()
        assert p["period_from"] == D(7) and p["period_to"] == D(372) and p["cycle"] == "annual"

    def test_preview_404(self, sa):
        assert requests.get(url("nope-" + uuid.uuid4().hex), headers=sa).status_code == 404


class TestValidation:
    def test_requires_confirm(self, sa):
        c = mk(sa)
        assert requests.post(url(c["id"]), headers=sa, json={}).status_code == 400
        assert requests.post(url(c["id"]), headers=sa, json={"confirm": "yes"}).status_code == 400
        assert mdb.invoices.count_documents({"company_id": c["id"]}) == 0

    @pytest.mark.parametrize("st", ["paused", "cancelled", "past_due"])
    def test_bad_status(self, sa, st):
        c = mk(sa)
        mdb.companies.update_one({"id": c["id"]}, {"$set": {"status": st}})
        r = requests.post(url(c["id"]), headers=sa, json={"confirm": True})
        assert r.status_code == 400, r.text

    def test_no_card(self, sa):
        c = mk(sa, card=None)
        mdb.companies.update_one({"id": c["id"]}, {"$unset": {"card": ""}})
        r = requests.post(url(c["id"]), headers=sa, json={"confirm": True})
        assert r.status_code == 400 and "tarjeta" in r.json()["detail"].lower()

    def test_pending_invoice_blocks(self, sa):
        c = mk(sa)
        mdb.invoices.insert_one({"id": str(uuid.uuid4()), "company_id": c["id"], "number": "TST-P", "date": TODAY, "items": [],
                                 "subtotal": 10, "tax": 0, "total": 10, "currency": "GTQ", "status": "pending", "kind": "subscription",
                                 "created_at": datetime.utcnow().isoformat()})
        r = requests.post(url(c["id"]), headers=sa, json={"confirm": True})
        assert r.status_code == 400 and "pendiente" in r.json()["detail"].lower()

    def test_non_superadmin_403(self, sa):
        c = mk(sa)
        h = login(c["email"], PW)
        assert requests.get(url(c["id"]), headers=h).status_code == 403
        assert requests.post(url(c["id"]), headers=h, json={"confirm": True}).status_code == 403
        h2 = login("admin@bellavida.com", "Demo2026!")
        assert requests.post(url(c["id"]), headers=h2, json={"confirm": True}).status_code == 403
        assert requests.get(url(c["id"])).status_code in (401, 403)


class TestSuccess:
    def test_active_success(self, sa):
        c = mk(sa, next_billing_date=D(12))
        pv = requests.get(url(c["id"]), headers=sa).json()
        r = requests.post(url(c["id"]), headers=sa, json={"confirm": True})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True and d["next_billing_date"] == D(42) and d["total"] == pv["total"]
        inv = mdb.invoices.find_one({"company_id": c["id"], "kind": "advance"}, {"_id": 0})
        assert inv["status"] == "paid" and inv["period_from"] == D(12) and inv["period_to"] == D(42) and inv["number"] == d["invoice"]
        pay = mdb.payments.find_one({"invoice_id": inv["id"]}, {"_id": 0})
        assert pay["status"] == "approved" and pay["method"] == "card" and pay["amount"] == inv["total"]
        cc = co(c["id"])
        assert cc["next_billing_date"] == D(42) and cc["status"] == "active"
        st = requests.get(f"{BASE_URL}/api/admin/companies/{c['id']}/statement", headers=sa).json()
        assert st["balance"] == 0
        assert any(h["change"].startswith("Cobro adelantado") and "aprobado" in h["change"] for h in st["history"])
        ac = requests.get(f"{BASE_URL}/api/admin/companies/{c['id']}/account-statement", headers=sa,
                          params={"start": D(-30), "end": D(1)}).json()
        assert ac["closing"] == 0 and any(x["type"] == "cargo" and x["doc"] == inv["number"] for x in ac["rows"])
        assert any(x["type"] == "abono" and x["doc"] == inv["number"] for x in ac["rows"])
        # second advance chain: from the new next_billing_date
        p2 = requests.get(url(c["id"]), headers=sa).json()
        assert p2["period_from"] == D(42) and p2["period_to"] == D(72)

    def test_trial_becomes_active(self, sa):
        c = mk(sa, status="trial", trial_ends=D(5))
        r = requests.post(url(c["id"]), headers=sa, json={"confirm": True})
        assert r.status_code == 200, r.text
        cc = co(c["id"])
        assert cc["status"] == "active" and cc["next_billing_date"] == D(35) and cc.get("converted") is True


class TestRejected:
    def test_card_0002(self, sa):
        c = mk(sa, card="0002", next_billing_date=D(3))
        r = requests.post(url(c["id"]), headers=sa, json={"confirm": True})
        assert r.status_code == 402, r.text
        inv = mdb.invoices.find_one({"company_id": c["id"], "kind": "advance"}, {"_id": 0})
        assert inv["status"] == "void"
        pay = mdb.payments.find_one({"invoice_id": inv["id"]}, {"_id": 0})
        assert pay["status"] == "rejected"
        cc = co(c["id"])
        assert cc["status"] == "active" and cc["next_billing_date"] == D(3) and not cc.get("past_due_since")
        st = requests.get(f"{BASE_URL}/api/admin/companies/{c['id']}/statement", headers=sa).json()
        assert st["balance"] == 0
        assert any("rechazado" in h["change"] for h in st["history"])
        # retry not blocked by void invoice
        r2 = requests.post(url(c["id"]), headers=sa, json={"confirm": True})
        assert r2.status_code == 402

    def test_trial_card_0002_stays_trial(self, sa):
        c = mk(sa, status="trial", card="0002")
        r = requests.post(url(c["id"]), headers=sa, json={"confirm": True})
        assert r.status_code == 402
        assert co(c["id"])["status"] == "trial"
