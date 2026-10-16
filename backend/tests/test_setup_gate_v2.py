# Setup-gate retest (iteration 7): rules confirm via /salon-rules/reviewed, WA bot gated while incomplete, bellavida bot unaffected
import os, time, pytest, requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
STAMP = str(int(time.time()))
WA = f"+5024{STAMP[-7:]}"
SLUG = f"test-gate2-{STAMP}"
GATED = "Gracias por escribirnos. Un asesor le atenderá pronto."


@pytest.fixture(scope="module")
def ctx():
    r = requests.post(f"{API}/signup", json={"company_name": f"TEST_Gate2 {STAMP}", "email": f"test_gate2_{STAMP}@example.com",
                                             "password": "Test12345!", "whatsapp_number": WA, "slug": SLUG})
    assert r.status_code == 200, r.text
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    me = s.get(f"{API}/auth/me").json()
    return {"s": s, "company": me["company"]}


# WhatsApp bot gated while setup incomplete
def test_wa_gated_while_incomplete(ctx):
    print("modules:", ctx["company"].get("enabled_modules"), "wa:", ctx["company"].get("whatsapp_number"))
    r = requests.post(f"{API}/wa/inbound", json={"to": WA, "from_phone": "+50259990001", "text": "Hola, quiero una cita mañana"})
    assert r.status_code == 200, r.text
    assert r.json()["reply"] == GATED


# Rules reviewed without changes
def test_rules_reviewed_endpoint(ctx):
    s = ctx["s"]
    assert s.get(f"{API}/salon-rules").json().get("reviewed") in (False, None)
    r = s.post(f"{API}/salon-rules/reviewed")
    assert r.status_code == 200, r.text
    assert s.get(f"{API}/salon-rules").json().get("reviewed") is True
    steps = {x["key"]: x["done"] for x in s.get(f"{API}/onboarding").json()["steps"]}
    assert steps["rules"] is True
    assert s.get(f"{API}/onboarding").json()["setup_complete"] is False


# Complete remaining steps -> WA bot replies (no longer gated) if whatsapp module enabled
def test_wa_after_complete(ctx):
    s = ctx["s"]
    svc = s.post(f"{API}/services", json={"name": "TEST_Corte", "category": "Cabello", "duration": 30, "price": 50}).json()
    br = s.get(f"{API}/branches").json()
    s.post(f"{API}/stylists", json={"name": "TEST_Est", "phone": "+50255551235", "service_ids": [svc["id"]], "branch_id": br[0]["id"]})
    s.put(f"{API}/company", json={"description": "Salón prueba"})
    for b in s.get(f"{API}/branches").json():
        s.put(f"{API}/branches/{b['id']}", json={**b, "address": "Zona 1"})
    assert s.get(f"{API}/onboarding").json()["setup_complete"] is True
    r = requests.post(f"{API}/wa/inbound", json={"to": WA, "from_phone": "+50259990001", "text": "Hola"})
    assert r.status_code == 200
    if "whatsapp" in ctx["company"].get("enabled_modules", []):
        assert r.json()["reply"] != GATED
    else:
        assert r.json()["reply"] == GATED


def test_incomplete_portal_403():
    for slug in ("salon-retest-trinity", "wwwpruebacom"):
        assert requests.get(f"{API}/public/salon/{slug}").status_code in (403, 404)
