# Iteration 12: N1 skip setup guide + pending steps, N2 description/address/bank steps, N3 portal cancel-preview policy
import os, time, datetime as dt, pytest, requests, jwt
from pathlib import Path

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
STAMP = str(int(time.time()))
SLUG = f"test-skip-{STAMP}"
ENV = dict(l.split("=", 1) for l in Path("/app/backend/.env").read_text().splitlines() if "=" in l)
JWT_SECRET = ENV["JWT_SECRET"].strip().strip('"')


def keys(s):
    return [p["key"] for p in s.get(f"{API}/onboarding").json()["pending"]]


@pytest.fixture(scope="module")
def ctx():
    r = requests.post(f"{API}/signup", json={"company_name": f"TEST_Skip {STAMP}", "email": f"test_skip_{STAMP}@example.com",
                                             "password": "Test12345!", "whatsapp_number": f"+5023{STAMP[-7:]}", "slug": SLUG})
    assert r.status_code == 200, r.text
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return {"s": s}


# N1: initial state, pending list contains all required steps incl. bank (deposit enabled default)
def test_initial_pending(ctx):
    d = ctx["s"].get(f"{API}/onboarding").json()
    assert d["skipped"] is False and d["setup_complete"] is False
    assert d["required"] == ["services", "stylists", "description", "address", "rules", "bank"]
    assert [p["key"] for p in d["pending"]] == d["required"]
    for p in d["pending"]:
        assert p["hint"] and p["to"]
    addr = next(p for p in d["pending"] if p["key"] == "address")
    assert "Falta la dirección de" in addr["hint"], addr
    assert next(p for p in d["pending"] if p["key"] == "description")["to"] == "/app/config?focus=description"
    assert next(p for p in d["pending"] if p["key"] == "bank")["to"] == "/app/config?tab=reglas&focus=bank_name"


# N1.6: portal paused
def test_public_403_preparando(ctx):
    r = requests.get(f"{API}/public/salon/{SLUG}")
    assert r.status_code == 403 and "preparando" in r.text


# N1.8: share before ready -> 400
def test_share_before_ready(ctx):
    r = ctx["s"].post(f"{API}/onboarding", json={"shared": True})
    assert r.status_code == 400, r.text


# N1.1: skip + audit
def test_skip_and_audit(ctx):
    s = ctx["s"]
    assert s.post(f"{API}/onboarding", json={"skipped": True}).status_code == 200
    assert s.get(f"{API}/onboarding").json()["skipped"] is True
    logs = s.get(f"{API}/audit").json()
    assert any("Guía de arranque omitida" in str(l) for l in logs)
    me = s.get(f"{API}/auth/me").json()
    print("me.company onboarding:", (me.get("company") or {}).get("onboarding"))


# N1.5: services step completes and pending shrinks
def test_service_completes_step(ctx):
    s = ctx["s"]
    r = s.post(f"{API}/services", json={"name": "TEST_Corte", "category": "Cabello", "duration": 30, "price": 50})
    assert r.status_code == 200, r.text
    ctx["svc"] = r.json()["id"]
    assert "services" not in keys(s)


# N1.9: bank pending; disabling deposit removes step; re-enable + fill bank completes
def test_bank_step(ctx):
    s = ctx["s"]
    assert "bank" in keys(s)
    r = s.put(f"{API}/salon-rules", json={"values": {"deposit_enabled": False}})
    assert r.status_code == 200, r.text
    d = s.get(f"{API}/onboarding").json()
    assert "bank" not in d["required"] and "rules" not in keys(s)
    s.put(f"{API}/salon-rules", json={"values": {"deposit_enabled": True}})
    assert "bank" in keys(s)
    s.put(f"{API}/salon-rules", json={"values": {"bank_name": "TEST_Banco"}})
    assert "bank" in keys(s)  # account still missing
    s.put(f"{API}/salon-rules", json={"values": {"bank_account": "123-456"}})
    assert "bank" not in keys(s)


# N2: description and address are separate steps
def test_description_and_address(ctx):
    s = ctx["s"]
    s.put(f"{API}/company", json={"description": "Salón TEST"})
    k = keys(s)
    assert "description" not in k and "address" in k
    brs = s.get(f"{API}/branches").json()
    for b in brs:
        s.put(f"{API}/branches/{b['id']}", json={**b, "address": "Zona 1"})
    assert keys(s) == ["stylists"]


# N1.7: last step -> complete, portal 200, share allowed
def test_complete_all(ctx):
    s = ctx["s"]
    br = s.get(f"{API}/branches").json()
    r = s.post(f"{API}/stylists", json={"name": "TEST_Est", "phone": "+50255551299", "service_ids": [ctx["svc"]], "branch_id": br[0]["id"]})
    assert r.status_code == 200, r.text
    d = s.get(f"{API}/onboarding").json()
    assert d["setup_complete"] is True and d["pending"] == []
    assert requests.get(f"{API}/public/salon/{SLUG}").status_code == 200
    assert s.post(f"{API}/onboarding", json={"shared": True}).status_code == 200


# Cleanup TEST_ company via super admin
def test_cleanup(ctx):
    sa = requests.post(f"{API}/auth/login", json={"email": "mario.rivera@gmail.com", "password": "Admin2026!"}).json()["token"]
    h = {"Authorization": f"Bearer {sa}"}
    cos = requests.get(f"{API}/admin/companies", headers=h).json()
    cos = cos if isinstance(cos, list) else cos.get("items", [])
    for c in cos:
        if c.get("slug") == SLUG:
            r = requests.delete(f"{API}/admin/companies/{c['id']}", headers=h, json={"confirm": "ELIMINAR"})
            print("delete", r.status_code, r.text[:200])


# ---------- N3 portal cancel-preview on bellavida ----------
PHONE = f"+5025{STAMP[-7:]}"


@pytest.fixture(scope="module")
def bv():
    t = requests.post(f"{API}/auth/login", json={"email": "admin@bellavida.com", "password": "Demo2026!"}).json()["token"]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {t}"})
    pub = requests.get(f"{API}/public/salon/bellavida").json()
    cid = s.get(f"{API}/auth/me").json()["company"]["id"]
    tok = jwt.encode({"sub": PHONE, "cid": cid, "type": "client", "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=30)}, JWT_SECRET, "HS256")
    out = {"s": s, "pub": pub, "ctok": tok, "appts": []}
    yield out
    for a in out["appts"]:
        s.post(f"{API}/appointments/{a}/status", json={"status": "cancelled", "reason": "TEST cleanup"})


def book(bv, day_offset, prefer_early):
    br, svc = bv["pub"]["branches"][0]["id"], bv["pub"]["services"][0]["id"]
    for off in ([day_offset] if not prefer_early else [day_offset, day_offset + 1]):
        date = (dt.date.today() + dt.timedelta(days=off)).isoformat()
        slots = requests.get(f"{API}/public/salon/bellavida/slots", params={"branch_id": br, "service_id": svc, "date": date}).json()["slots"]
        if not slots:
            continue
        sl = slots[0] if prefer_early else slots[-1]
        t = sl["time"] if isinstance(sl, dict) else sl
        r = bv["s"].post(f"{API}/appointments", json={"branch_id": br, "service_id": svc, "date": date, "time": t, "phone": PHONE, "name": "TEST_Portal Cancel",
                                                       "stylist_id": sl.get("stylist_id") if isinstance(sl, dict) else None})
        if r.status_code == 200:
            bv["appts"].append(r.json()["id"])
            return r.json()
        print("book fail", r.status_code, r.text[:200])
    pytest.skip("no slot")


def test_cancel_preview_far(bv):
    a = book(bv, 4, False)
    r = requests.get(f"{API}/public/salon/bellavida/appointments/{a['id']}/cancel-preview", headers={"X-Client-Token": bv["ctok"]})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["late"] is False and p["hours_before"] > 24
    assert "sin penalización" in p["client_consequence"]
    assert p["cancel_hours"] == 24 and "24 horas" in p["policy_text"]


def test_cancel_preview_late(bv):
    a = book(bv, 1, True)
    r = requests.get(f"{API}/public/salon/bellavida/appointments/{a['id']}/cancel-preview", headers={"X-Client-Token": bv["ctok"]})
    p = r.json()
    print("late preview:", a["date"], a["time"], p)
    if p["hours_before"] >= 24:
        pytest.skip("no slot within 24h")
    assert p["late"] is True and "tardía" in p["client_consequence"]


def test_cancel_preview_auth(bv):
    aid = bv["appts"][0]
    assert requests.get(f"{API}/public/salon/bellavida/appointments/{aid}/cancel-preview").status_code == 401
    other = jwt.encode({"sub": "+50250000000", "cid": jwt.decode(bv["ctok"], JWT_SECRET, ["HS256"])["cid"], "type": "client",
                        "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=30)}, JWT_SECRET, "HS256")
    assert requests.get(f"{API}/public/salon/bellavida/appointments/{aid}/cancel-preview", headers={"X-Client-Token": other}).status_code == 404


def test_bellavida_complete(bv):
    d = bv["s"].get(f"{API}/onboarding").json()
    assert d["setup_complete"] is True and d["pending"] == [] or d["setup_complete"] is True
    print("bellavida pending (sticky complete):", [p["key"] for p in d["pending"]])
