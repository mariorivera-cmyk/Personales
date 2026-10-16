# Setup-gate (guía de arranque obligatoria) tests: signup -> incomplete -> portal 403 -> complete steps -> portal 200 -> persisted
import os, time, pytest, requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
STAMP = str(int(time.time()))
EMAIL = f"test_setupapi_{STAMP}@example.com"
SLUG = f"test-setup-api-{STAMP}"


@pytest.fixture(scope="module")
def ctx():
    r = requests.post(f"{API}/signup", json={"company_name": f"TEST_Setup API {STAMP}", "email": EMAIL, "password": "Test12345!",
                                             "whatsapp_number": f"+5025{STAMP[-7:]}", "slug": SLUG})
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return {"s": s}


def test_new_company_incomplete(ctx):
    me = ctx["s"].get(f"{API}/auth/me").json()
    assert not me["company"].get("setup_complete")
    ob = ctx["s"].get(f"{API}/onboarding").json()
    assert ob["setup_complete"] is False
    assert ob["required"] == ["services", "stylists", "salon", "rules"]
    assert ob["dismissed"] is False
    done = {s["key"]: s["done"] for s in ob["steps"]}
    assert not any(done[k] for k in ob["required"])


def test_portal_blocked_while_incomplete(ctx):
    r = requests.get(f"{API}/public/salon/{SLUG}")
    assert r.status_code == 403
    assert "preparando su portal" in r.json()["detail"]
    r2 = requests.get(f"{API}/public/salon/{SLUG}/slots", params={"date": "2026-02-02", "branch_id": "x", "service_id": "x"})
    assert r2.status_code == 403


def test_dismiss_ignored_while_incomplete(ctx):
    ctx["s"].post(f"{API}/onboarding", json={"dismissed": True})
    ob = ctx["s"].get(f"{API}/onboarding").json()
    assert ob["dismissed"] is False
    ctx["s"].post(f"{API}/onboarding", json={"dismissed": False})


def test_complete_steps(ctx):
    s = ctx["s"]
    r = s.post(f"{API}/services", json={"name": "TEST_Corte", "category": "Cabello", "duration": 30, "price": 50})
    assert r.status_code in (200, 201), r.text
    ctx["svc"] = r.json()["id"]
    assert s.get(f"{API}/onboarding").json()["setup_complete"] is False
    r = s.post(f"{API}/stylists", json={"name": "TEST_Estilista", "phone": "+50255551234", "service_ids": [ctx["svc"]]})
    assert r.status_code in (200, 201), r.text
    r = s.put(f"{API}/company", json={"description": "Salón de prueba"})
    assert r.status_code == 200
    br = s.get(f"{API}/branches").json()
    for b in br:
        r = s.put(f"{API}/branches/{b['id']}", json={**b, "address": "6a Av 1-23 Zona 1"})
        assert r.status_code == 200, r.text
    ob = s.get(f"{API}/onboarding").json()
    done = {x["key"]: x["done"] for x in ob["steps"]}
    assert done["services"] and done["stylists"] and done["salon"] and not done["rules"]
    assert ob["setup_complete"] is False
    r = s.post(f"{API}/salon-rules/reviewed")
    assert r.status_code == 200
    ob = s.get(f"{API}/onboarding").json()
    assert ob["setup_complete"] is True
    me = s.get(f"{API}/auth/me").json()
    assert me["company"]["setup_complete"] is True


def test_portal_open_after_complete(ctx):
    r = requests.get(f"{API}/public/salon/{SLUG}")
    assert r.status_code == 200, r.text
    assert r.json()["slug"] == SLUG


def test_dismiss_and_share_after_complete(ctx):
    s = ctx["s"]
    s.post(f"{API}/onboarding", json={"shared": True})
    ob = s.get(f"{API}/onboarding").json()
    assert {x["key"]: x["done"] for x in ob["steps"]}["share"] is True
    s.post(f"{API}/onboarding", json={"dismissed": True})
    assert s.get(f"{API}/onboarding").json()["dismissed"] is True


def test_setup_complete_sticky(ctx):
    s = ctx["s"]
    for st in s.get(f"{API}/stylists").json():
        s.delete(f"{API}/stylists/{st['id']}")
    r = s.delete(f"{API}/services/{ctx['svc']}")
    assert r.status_code in (200, 204), r.text
    ob = s.get(f"{API}/onboarding").json()
    assert ob["setup_complete"] is True
    assert requests.get(f"{API}/public/salon/{SLUG}").status_code == 200


def test_bellavida_unaffected():
    r = requests.post(f"{API}/auth/login", json={"email": "admin@bellavida.com", "password": "Demo2026!"})
    assert r.status_code == 200
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    assert requests.get(f"{API}/auth/me", headers=h).json()["company"]["setup_complete"] is True
    assert requests.get(f"{API}/onboarding", headers=h).json()["setup_complete"] is True
    assert requests.get(f"{API}/public/salon/bellavida").status_code == 200


def test_user_locked_companies_still_locked():
    for slug in ("salon-retest-trinity", "wwwpruebacom"):
        r = requests.get(f"{API}/public/salon/{slug}")
        assert r.status_code in (403, 404), (slug, r.status_code)
