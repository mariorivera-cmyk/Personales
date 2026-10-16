# Company status (trial/active/paused/cancelled), delete with security word, cron purge
import os
import uuid
import time
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
CRON_SECRET = _env("/app/backend/.env", "WEBHOOK_CRON_SECRET")
mdb = MongoClient(_env("/app/backend/.env", "MONGO_URL"))[_env("/app/backend/.env", "DB_NAME")]
TODAY = datetime.now(ZoneInfo("America/Guatemala")).strftime("%Y-%m-%d")
PROTECTED = {"bellavida", "salon-retest-trinity", "wwwpruebacom"}
PW = "TestPass2026!"


def login(email, pw):
    return requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw})


@pytest.fixture(scope="module")
def sa():
    r = login("mario.rivera@gmail.com", "Admin2026!")
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def plan_id(sa):
    return requests.get(f"{BASE_URL}/api/admin/plans", headers=sa).json()[0]["id"]


created = []


def make_company(sa, plan_id):
    s = uuid.uuid4().hex[:6]
    body = {"company_name": f"TEST_Co {s}", "slug": f"test-co-{s}", "email": f"test_co_{s}@example.com", "password": PW,
            "plan_id": plan_id, "whatsapp_number": f"+50299{s[:3].encode().hex()[:6]}", "status": "trial", "modules": ["portal"]}
    r = requests.post(f"{BASE_URL}/api/admin/companies", headers=sa, json=body)
    assert r.status_code == 200, r.text
    c = r.json()
    created.append(c["id"])
    return c, body["email"]


@pytest.fixture(scope="module", autouse=True)
def cleanup(sa):
    yield
    for cid in created:
        requests.delete(f"{BASE_URL}/api/admin/companies/{cid}", headers=sa, json={"confirm": "ELIMINAR"})
    for c in mdb.companies.find({"name": {"$regex": "^TEST_Co"}}):
        requests.delete(f"{BASE_URL}/api/admin/companies/{c['id']}", headers=sa, json={"confirm": "ELIMINAR"})


def status(sa, cid, st, reason=""):
    return requests.post(f"{BASE_URL}/api/admin/companies/{cid}/status", headers=sa, json={"status": st, "reason": reason})


class TestStatus:
    def test_transitions_and_history(self, sa, plan_id):
        c, email = make_company(sa, plan_id)
        cid = c["id"]
        r = status(sa, cid, "active")
        assert r.status_code == 200 and r.json()["status"] == "active"
        r = status(sa, cid, "trial", "TEST motivo")
        d = r.json()
        assert d["status"] == "trial"
        assert d["trial_ends"] == (datetime.strptime(TODAY, "%Y-%m-%d") + timedelta(days=30)).strftime("%Y-%m-%d")
        r = status(sa, cid, "paused")
        assert r.json()["status"] == "paused" and r.json().get("paused_at")
        r = status(sa, cid, "cancelled")
        d = r.json()
        assert d["status"] == "cancelled" and d.get("cancelled_at")
        assert d["purge_after"] == (datetime.strptime(TODAY, "%Y-%m-%d") + timedelta(days=60)).strftime("%Y-%m-%d")
        r = status(sa, cid, "active")
        assert "purge_after" not in r.json()
        status(sa, cid, "cancelled")
        r = status(sa, cid, "trial")
        assert "purge_after" not in r.json()
        hist = requests.get(f"{BASE_URL}/api/admin/companies/{cid}/statement", headers=sa).json()["history"]
        changes = [h["change"] for h in hist]
        assert any(x.startswith("Estado: Activa → Prueba (30 días) (TEST motivo)") for x in changes), changes
        assert any("Estado: En pausa → Cancelada" in x for x in changes)

    def test_invalid_status_and_404(self, sa, plan_id):
        c, _ = make_company(sa, plan_id)
        assert status(sa, c["id"], "bogus").status_code == 400
        assert status(sa, "nope_nope", "active").status_code == 404

    def test_non_super_admin_403(self, sa, plan_id):
        c, email = make_company(sa, plan_id)
        tok = login(email, PW).json()["token"]
        r = requests.post(f"{BASE_URL}/api/admin/companies/{c['id']}/status", headers={"Authorization": f"Bearer {tok}"}, json={"status": "active"})
        assert r.status_code == 403
        r = requests.delete(f"{BASE_URL}/api/admin/companies/{c['id']}", headers={"Authorization": f"Bearer {tok}"}, json={"confirm": "ELIMINAR"})
        assert r.status_code == 403

    @pytest.mark.parametrize("st,word", [("paused", "pausa"), ("cancelled", "cancelada")])
    def test_blocked_access(self, sa, plan_id, st, word):
        c, email = make_company(sa, plan_id)
        cid = c["id"]
        tok = login(email, PW).json()["token"]
        h = {"Authorization": f"Bearer {tok}"}
        assert requests.get(f"{BASE_URL}/api/dashboard", headers=h).status_code == 200
        status(sa, cid, st)
        r = login(email, PW)
        assert r.status_code == 403 and word in r.json()["detail"], r.text
        r = requests.get(f"{BASE_URL}/api/dashboard", headers=h)
        assert r.status_code == 403, r.text
        r = requests.get(f"{BASE_URL}/api/public/salon/{c['slug']}")
        assert r.status_code == 403, r.text
        # super admin still enters
        r = requests.get(f"{BASE_URL}/api/dashboard", headers={**sa, "X-Company-Id": cid})
        assert r.status_code == 200, r.text
        status(sa, cid, "active")
        assert login(email, PW).status_code == 200
        assert requests.get(f"{BASE_URL}/api/dashboard", headers=h).status_code == 200


class TestDelete:
    def test_wrong_word_and_delete(self, sa, plan_id):
        c, email = make_company(sa, plan_id)
        cid = c["id"]
        h = {**sa, "X-Company-Id": cid}
        rs = requests.post(f"{BASE_URL}/api/clients", headers=h, json={"name": "TEST_Cli", "phone": "+50288887777"})
        assert mdb.users.count_documents({"company_id": cid}) >= 1
        assert mdb.branches.count_documents({"company_id": cid}) >= 1
        for w in (None, "eliminar", "BORRAR"):
            body = {"confirm": w} if w else {}
            r = requests.delete(f"{BASE_URL}/api/admin/companies/{cid}", headers=sa, json=body)
            assert r.status_code == 400, r.text
        r = requests.delete(f"{BASE_URL}/api/admin/companies/{cid}", headers=sa)
        assert r.status_code == 400
        r = requests.delete(f"{BASE_URL}/api/admin/companies/{cid}", headers=sa, json={"confirm": "ELIMINAR"})
        assert r.status_code == 200 and r.json()["ok"]
        assert mdb.companies.count_documents({"id": cid}) == 0
        for coll in mdb.list_collection_names():
            if coll != "deleted_companies":
                assert mdb[coll].count_documents({"company_id": cid}) == 0, coll
        assert mdb.deleted_companies.find_one({"company_id": cid, "reason": "manual"})
        assert login(email, PW).status_code == 401
        r = requests.delete(f"{BASE_URL}/api/admin/companies/{cid}", headers=sa, json={"confirm": "ELIMINAR"})
        assert r.status_code == 404


class TestCron:
    def test_auth(self):
        assert requests.post(f"{BASE_URL}/api/cron/purge-cancelled", json={}).status_code == 401
        assert requests.post(f"{BASE_URL}/api/cron/purge-cancelled", json={}, headers={"Authorization": "Bearer wrong"}).status_code == 401

    def test_no_body(self):
        rid = "TEST_run_" + uuid.uuid4().hex
        r = requests.post(f"{BASE_URL}/api/cron/purge-cancelled", headers={"Authorization": f"Bearer {CRON_SECRET}", "X-Webhook-Id": rid})
        print("no-body status", r.status_code, r.text)
        assert r.status_code == 200, r.text

    def test_purge(self, sa, plan_id):
        old, _ = make_company(sa, plan_id)
        fut, _ = make_company(sa, plan_id)
        paused, _ = make_company(sa, plan_id)
        status(sa, old["id"], "cancelled")
        status(sa, fut["id"], "cancelled")
        status(sa, paused["id"], "paused")
        mdb.companies.update_one({"id": old["id"]}, {"$set": {"purge_after": "2020-01-01"}})
        mdb.companies.update_one({"id": paused["id"]}, {"$set": {"purge_after": "2020-01-01"}})
        rid = "TEST_run_" + uuid.uuid4().hex
        h = {"Authorization": f"Bearer {CRON_SECRET}", "X-Webhook-Id": rid}
        t = time.time()
        r = requests.post(f"{BASE_URL}/api/cron/purge-cancelled", headers=h, json={"run_id": rid})
        assert r.status_code == 200 and r.json().get("ok") and not r.json().get("duplicate")
        assert time.time() - t < 5
        r2 = requests.post(f"{BASE_URL}/api/cron/purge-cancelled", headers=h, json={"run_id": rid})
        assert r2.status_code == 200 and r2.json().get("duplicate") is True
        time.sleep(4)
        assert mdb.companies.count_documents({"id": old["id"]}) == 0
        assert mdb.users.count_documents({"company_id": old["id"]}) == 0
        assert mdb.deleted_companies.find_one({"company_id": old["id"], "by": "sistema"})
        assert mdb.companies.count_documents({"id": fut["id"]}) == 1
        assert mdb.companies.count_documents({"id": paused["id"]}) == 1
        for slug in PROTECTED:
            assert mdb.companies.count_documents({"slug": slug}) == 1, slug
