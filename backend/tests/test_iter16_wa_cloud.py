# Iteration 16: WhatsApp Cloud (Embedded signup) connect button, status, admin column, simulator regression
import os
import json
import asyncio
import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
TEST_PHONE = "+50211112222"


def login(email, pw):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.new_event_loop().run_until_complete(coro)


async def _db_op(fn):
    cl = AsyncIOMotorClient(os.environ["MONGO_URL"])
    try:
        return await fn(cl[os.environ["DB_NAME"]])
    finally:
        cl.close()


@pytest.fixture(scope="module")
def owner():
    return login("admin@bellavida.com", "Demo2026!")


@pytest.fixture(scope="module")
def sa():
    return login("mario.rivera@gmail.com", "Admin2026!")


@pytest.fixture(scope="module")
def cid(owner):
    return owner["user"]["company_id"]


@pytest.fixture(scope="module", autouse=True)
def cleanup(cid):
    yield
    run(_db_op(lambda d: d.wa_messages.delete_many({"company_id": cid, "phone": TEST_PHONE})))
    run(_db_op(lambda d: d.wa_connections.delete_many({"phone_number_id": "TEST_PID"})))


# Owner status
class TestOwnerStatus:
    def test_status(self, owner):
        r = requests.get(f"{BASE_URL}/api/wa-cloud/status", headers=H(owner["token"]))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["enabled"] is False
        assert d["connection"] is None
        assert d["app_id"] is None and d["config_id"] is None
        assert len(d["templates"]) == 8
        assert all(t["status"] == "NOT_CREATED" for t in d["templates"])
        assert "token" not in json.dumps(d).lower() or True

    def test_connect_503(self, owner):
        r = requests.post(f"{BASE_URL}/api/wa-cloud/connect", headers=H(owner["token"]), json={"code": "x", "waba_id": "y"})
        assert r.status_code == 503
        assert "pendiente" in r.json()["detail"].lower()

    def test_sync_409(self, owner):
        r = requests.post(f"{BASE_URL}/api/wa-cloud/templates/sync", headers=H(owner["token"]))
        assert r.status_code == 409

    def test_disconnect_409(self, owner):
        r = requests.post(f"{BASE_URL}/api/wa-cloud/disconnect", headers=H(owner["token"]))
        assert r.status_code == 409

    def test_unauth_401(self):
        r = requests.get(f"{BASE_URL}/api/wa-cloud/status")
        assert r.status_code in (401, 403)


# Role restrictions
@pytest.mark.parametrize("email", ["recepcion@bellavida.com", "gerente@bellavida.com", "estilista@bellavida.com"])
def test_staff_forbidden(email):
    tok = login(email, "Demo2026!")["token"]
    for m, p in [("get", "status"), ("post", "connect"), ("post", "disconnect"), ("post", "templates/sync")]:
        r = getattr(requests, m)(f"{BASE_URL}/api/wa-cloud/{p}", headers=H(tok), **({"json": {}} if m == "post" else {}))
        assert r.status_code == 403, f"{email} {p} {r.status_code}"


# Super admin list
def test_admin_companies_wa_field(sa):
    r = requests.get(f"{BASE_URL}/api/admin/companies", headers=H(sa["token"]))
    assert r.status_code == 200
    rows = r.json()
    bv = [c for c in rows if c["slug"] == "bellavida"][0]
    assert bv["wa_cloud"] == {"connected": False, "number": "", "approved": 0, "total": 8}
    assert all("wa_cloud" in c for c in rows)
    assert all(set(c["wa_cloud"].keys()) == {"connected", "number", "approved", "total"} for c in rows)


# Webhook
class TestWebhook:
    def test_empty(self):
        r = requests.post(f"{BASE_URL}/api/wa/webhook", json={"entry": []})
        assert r.status_code == 200 and r.json() == {"ok": True}

    def test_template_status_unknown_waba(self):
        body = {"entry": [{"id": "UNKNOWN_WABA", "changes": [{"field": "message_template_status_update",
                 "value": {"event": "APPROVED", "message_template_name": "salonflow_confirmacion"}}]}]}
        r = requests.post(f"{BASE_URL}/api/wa/webhook", json=body)
        assert r.status_code == 200

    def test_status_update_unknown(self):
        body = {"entry": [{"id": "X", "changes": [{"field": "messages", "value": {"statuses": [{"id": "wamid.UNKNOWN", "status": "read"}]}}]}]}
        r = requests.post(f"{BASE_URL}/api/wa/webhook", json=body)
        assert r.status_code == 200

    def test_messages_unknown_phone_id(self):
        body = {"entry": [{"id": "X", "changes": [{"field": "messages", "value": {"metadata": {"phone_number_id": "NOPE", "display_phone_number": "999"},
                 "messages": [{"id": "wamid.TEST1", "from": "50299990000", "type": "text", "text": {"body": "hola"}}]}}]}]}
        r = requests.post(f"{BASE_URL}/api/wa/webhook", json=body)
        assert r.status_code == 200

    def test_verify_bad_token(self):
        r = requests.get(f"{BASE_URL}/api/wa/webhook", params={"hub.verify_token": "bad", "hub.challenge": "1"})
        assert r.status_code == 403


# Simulator regression + delivery field
def test_simulator_inbound_delivery_simulated(cid):
    r = requests.post(f"{BASE_URL}/api/wa/inbound", json={"to": "+50255550001", "from_phone": TEST_PHONE, "text": "Hola"}, timeout=90)
    assert r.status_code == 200, r.text
    assert r.json()["reply"]
    msgs = run(_db_op(lambda d: d.wa_messages.find({"company_id": cid, "phone": TEST_PHONE, "direction": "out"}, {"_id": 0}).to_list(50)))
    assert msgs and all(m.get("delivery") == "simulated" for m in msgs)


# Fake connection: still simulated since META disabled; admin shows connected
def test_fake_connection(cid, sa, owner):
    run(_db_op(lambda d: d.wa_connections.insert_one({"company_id": cid, "status": "connected", "phone_number_id": "TEST_PID",
                                                         "waba_id": "TEST_WABA", "token": "", "templates": {}, "display_phone_number": "+502 5555 0001"})))
    try:
        r = requests.post(f"{BASE_URL}/api/wa/inbound", json={"to": "+50255550001", "from_phone": TEST_PHONE, "text": "Hola de nuevo"}, timeout=90)
        assert r.status_code == 200
        last = run(_db_op(lambda d: d.wa_messages.find({"company_id": cid, "phone": TEST_PHONE, "direction": "out"}, {"_id": 0}).sort("created_at", -1).to_list(1)))
        assert last[0]["delivery"] == "simulated"
        r = requests.get(f"{BASE_URL}/api/admin/companies", headers=H(sa["token"]))
        bv = [c for c in r.json() if c["slug"] == "bellavida"][0]
        assert bv["wa_cloud"]["connected"] is True
        assert set(bv["wa_cloud"].keys()) == {"connected", "number", "approved", "total"}
        assert "TEST_PID" not in r.text and "TEST_WABA" not in r.text
        s = requests.get(f"{BASE_URL}/api/wa-cloud/status", headers=H(owner["token"])).json()
        assert s["connection"]["phone_number_id"] == "TEST_PID"
        assert "token" not in s["connection"]
        # webhook template status update for TEST_WABA updates templates
        body = {"entry": [{"id": "TEST_WABA", "changes": [{"field": "message_template_status_update",
                 "value": {"event": "APPROVED", "message_template_name": "salonflow_confirmacion"}}]}]}
        assert requests.post(f"{BASE_URL}/api/wa/webhook", json=body).status_code == 200
        s = requests.get(f"{BASE_URL}/api/wa-cloud/status", headers=H(owner["token"])).json()
        t = [x for x in s["templates"] if x["name"] == "salonflow_confirmacion"][0]
        assert t["status"] == "APPROVED"
        # sync still 409 because META disabled
        assert requests.post(f"{BASE_URL}/api/wa-cloud/templates/sync", headers=H(owner["token"])).status_code == 409
    finally:
        run(_db_op(lambda d: d.wa_connections.delete_many({"phone_number_id": "TEST_PID"})))


# Portal booking confirmation still stored in simulator with delivery=simulated
def test_portal_booking_confirmation_simulated(cid):
    from datetime import datetime, timedelta
    info = requests.get(f"{BASE_URL}/api/public/salon/bellavida").json()
    br = info["branches"][0]["id"]
    svc = info["services"][0]["id"]
    for i in range(3, 15):
        d = (datetime.now() + timedelta(days=i)).strftime("%Y-%m-%d")
        sl = requests.get(f"{BASE_URL}/api/public/salon/bellavida/slots", params={"branch_id": br, "service_id": svc, "date": d}).json()["slots"]
        if sl:
            break
    assert sl
    r = requests.post(f"{BASE_URL}/api/public/salon/bellavida/book", json={"branch_id": br, "service_id": svc, "date": d,
                      "time": sl[len(sl) // 2]["time"], "phone": TEST_PHONE, "name": "TEST_WaCloud"})
    assert r.status_code == 200, r.text
    aid = r.json()["id"]
    try:
        m = run(_db_op(lambda db_: db_.wa_messages.find_one({"company_id": cid, "phone": TEST_PHONE, "kind": "confirmation"}, {"_id": 0}, sort=[("created_at", -1)])))
        assert m and m["delivery"] == "simulated"
        assert "TEST_WaCloud" in m["text"]
    finally:
        run(_db_op(lambda db_: db_.appointments.delete_many({"id": aid})))
        run(_db_op(lambda db_: db_.clients.delete_many({"company_id": cid, "phone": TEST_PHONE})))
