# Manual payments (register/void) + account statement (admin & company side)
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
D = lambda n: (TD - timedelta(days=n)).strftime("%Y-%m-%d")
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


def add_inv(cid, total, date, status="pending", number=None):
    iid = str(uuid.uuid4())
    mdb.invoices.insert_one({"id": iid, "company_id": cid, "company_name": "TEST", "number": number or f"TST-{iid[:6]}", "date": date,
                             "items": [{"desc": "Plan TEST", "amount": total, "kind": "plan"}], "subtotal": total, "tax": 0, "total": total,
                             "currency": "GTQ", "status": status, "kind": "subscription", "created_at": datetime.utcnow().isoformat()})
    return iid


@pytest.fixture(scope="module")
def co(sa):
    plan = requests.get(f"{BASE_URL}/api/admin/plans", headers=sa).json()[0]["id"]
    s = uuid.uuid4().hex[:6]
    body = {"company_name": f"TEST_Pay {s}", "slug": f"test-pay-{s}", "email": f"test_pay_{s}@example.com", "password": PW,
            "plan_id": plan, "whatsapp_number": f"+50298{int(s, 16) % 1000000:06d}", "status": "active"}
    r = requests.post(f"{BASE_URL}/api/admin/companies", headers=sa, json=body)
    assert r.status_code == 200, r.text
    c = r.json()
    created.append(c["id"])
    return {**c, "email": body["email"]}


def mp(sa, **kw):
    return requests.post(f"{BASE_URL}/api/admin/payments/manual", headers=sa, json=kw)


def stmt(h, cid, **params):
    return requests.get(f"{BASE_URL}/api/admin/companies/{cid}/account-statement", headers=h, params=params)


class TestValidation:
    def test_no_company(self, sa):
        assert mp(sa, amount=10).status_code == 400

    @pytest.mark.parametrize("amt", [0, -5, "abc"])
    def test_bad_amount(self, sa, co, amt):
        assert mp(sa, company_id=co["id"], amount=amt).status_code == 400

    def test_future_date(self, sa, co):
        r = mp(sa, company_id=co["id"], amount=10, date=(TD + timedelta(days=1)).strftime("%Y-%m-%d"))
        assert r.status_code == 400

    def test_bad_method(self, sa, co):
        assert mp(sa, company_id=co["id"], amount=10, method="bitcoin").status_code == 400

    def test_invoice_not_pending(self, sa, co):
        iid = add_inv(co["id"], 50, D(3), "paid")
        assert mp(sa, company_id=co["id"], amount=50, invoice_id=iid).status_code == 400

    def test_company_admin_forbidden(self, co):
        h = login(co["email"], PW)
        assert mp(h, company_id=co["id"], amount=10).status_code == 403
        assert stmt(h, co["id"]).status_code == 403


class TestFlow:
    def test_full_and_partial_and_void(self, sa, co):
        cid = co["id"]
        mdb.companies.update_one({"id": cid}, {"$set": {"status": "past_due", "past_due_since": D(5)}})
        inv = add_inv(cid, 100, D(10))
        # partial
        r = mp(sa, company_id=cid, amount=40, invoice_id=inv, method="deposit", reference="B-1", date=D(5))
        assert r.status_code == 200, r.text
        p1 = r.json()
        assert p1["manual"] is True and p1["status"] == "approved" and p1["invoice_number"].startswith("TST-")
        assert mdb.invoices.find_one({"id": inv})["status"] == "pending"
        # remaining
        r = mp(sa, company_id=cid, amount=60, invoice_id=inv, method="cash", date=D(2))
        assert r.status_code == 200
        p2 = r.json()
        assert mdb.invoices.find_one({"id": inv})["status"] == "paid"
        assert mdb.companies.find_one({"id": cid})["status"] == "active"
        # payments list
        lst = requests.get(f"{BASE_URL}/api/admin/payments", headers=sa).json()
        assert any(x["id"] == p2["id"] for x in lst)
        # history
        st = requests.get(f"{BASE_URL}/api/admin/companies/{cid}/statement", headers=sa).json()
        assert any("Pago manual" in h.get("note", h.get("text", str(h))) for h in st["history"]), st["history"][:3]
        # void requires reason
        assert requests.post(f"{BASE_URL}/api/admin/payments/{p2['id']}/void", headers=sa, json={}).status_code == 400
        r = requests.post(f"{BASE_URL}/api/admin/payments/{p2['id']}/void", headers=sa, json={"reason": "TEST error"})
        assert r.status_code == 200
        assert mdb.payments.find_one({"id": p2["id"]})["status"] == "void"
        assert mdb.invoices.find_one({"id": inv})["status"] == "pending"
        # double void
        assert requests.post(f"{BASE_URL}/api/admin/payments/{p2['id']}/void", headers=sa, json={"reason": "x"}).status_code == 400

    def test_void_card_payment_rejected(self, sa):
        card = mdb.payments.find_one({"method": "card", "status": "approved"}, {"_id": 0})
        if not card:
            pytest.skip("no card payment")
        assert requests.post(f"{BASE_URL}/api/admin/payments/{card['id']}/void", headers=sa, json={"reason": "x"}).status_code == 400

    def test_on_account(self, sa, co):
        r = mp(sa, company_id=co["id"], amount=25, method="check", date=D(1))
        assert r.status_code == 200
        assert r.json()["invoice_id"] is None and r.json()["invoice_number"] == ""

    def test_failed_invoice_can_be_paid_manually(self, sa, co):
        """past_due companies have 'failed' invoices (card rejected) – they should be payable manually"""
        iid = add_inv(co["id"], 30, D(4), "failed")
        st = stmt(sa, co["id"]).json()
        listed = any(p["id"] == iid for p in st["pending_invoices"])
        r = mp(sa, company_id=co["id"], amount=30, invoice_id=iid)
        mdb.invoices.update_one({"id": iid}, {"$set": {"status": "void"}})
        if r.status_code == 200:
            mdb.payments.update_one({"id": r.json()["id"]}, {"$set": {"status": "void"}})
        assert listed and r.status_code == 200, f"listed={listed} status={r.status_code} {r.text}"


class TestStatement:
    def test_balances(self, sa, co):
        cid = co["id"]
        r = stmt(sa, cid, start=D(30), end=TODAY)
        assert r.status_code == 200
        d = r.json()
        bal = d["opening"]
        for row in d["rows"]:
            bal = round(bal + row["charge"] - row["payment"], 2)
            assert abs(row["balance"] - bal) < 0.01
        assert abs(d["closing"] - bal) < 0.01
        assert abs(d["closing"] - (d["opening"] + d["charges"] - d["payments"])) < 0.01
        # opening = movements before start
        d2 = stmt(sa, cid, start=D(3), end=TODAY).json()
        before = [x for x in d["rows"] if x["date"] < D(3)]
        exp = round(d["opening"] + sum(x["charge"] - x["payment"] for x in before), 2)
        assert abs(d2["opening"] - exp) < 0.01, (d2["opening"], exp)
        assert all(x["date"] >= D(3) for x in d2["rows"])

    def test_empty_period(self, sa, co):
        d = stmt(sa, co["id"], start="2020-01-01", end="2020-01-31").json()
        assert d["rows"] == [] and d["opening"] == 0

    def test_start_after_end(self, sa, co):
        assert stmt(sa, co["id"], start=TODAY, end=D(5)).status_code == 400

    def test_404(self, sa):
        assert stmt(sa, "nope").status_code == 404

    def test_pdf_xlsx(self, sa, co):
        r = stmt(sa, co["id"], start=D(30), end=TODAY, format="pdf")
        assert r.status_code == 200 and r.content[:4] == b"%PDF"
        r = stmt(sa, co["id"], start=D(30), end=TODAY, format="xlsx")
        assert r.status_code == 200 and r.content[:2] == b"PK"

    def test_company_side(self, co):
        h = login(co["email"], PW)
        r = requests.get(f"{BASE_URL}/api/billing/account-statement", headers=h, params={"start": D(30), "end": TODAY})
        assert r.status_code == 200 and r.json()["company"]["id"] == co["id"]
        r = requests.get(f"{BASE_URL}/api/billing/account-statement", headers=h, params={"format": "pdf"})
        assert r.content[:4] == b"%PDF"

    def test_receptionist_forbidden(self):
        h = login("recepcion@bellavida.com", "Demo2026!")
        assert requests.get(f"{BASE_URL}/api/billing/account-statement", headers=h).status_code == 403

    def test_bellavida_admin(self):
        h = login("admin@bellavida.com", "Demo2026!")
        r = requests.get(f"{BASE_URL}/api/billing/account-statement", headers=h, params={"start": "2020-01-01"})
        assert r.status_code == 200 and len(r.json()["rows"]) >= 2
