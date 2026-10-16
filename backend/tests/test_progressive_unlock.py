# Progressive setup unlock (iteration 8): GET /api/onboarding `current` advances services->stylists->salon->rules->None
import os, time, pytest, requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
STAMP = str(int(time.time()))


@pytest.fixture(scope="module")
def s():
    r = requests.post(f"{API}/signup", json={"company_name": f"TEST_Prog API {STAMP}", "email": f"test_progapi_{STAMP}@example.com",
                                             "password": "Test12345!", "whatsapp_number": f"+5025{STAMP[-7:]}", "slug": f"test-progapi-{STAMP}"})
    assert r.status_code == 200, r.text
    ss = requests.Session()
    ss.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return ss


def cur(s):
    d = s.get(f"{API}/onboarding").json()
    return d["current"], d["setup_complete"]


def test_progression(s):
    assert cur(s) == ("services", False)
    svc = s.post(f"{API}/services", json={"name": "TEST_Corte", "category": "Cabello", "duration": 30, "price": 50}).json()
    assert cur(s) == ("stylists", False)
    br = s.get(f"{API}/branches").json()
    s.post(f"{API}/stylists", json={"name": "TEST_Est", "service_ids": [svc["id"]], "branch_id": br[0]["id"]})
    assert cur(s) == ("salon", False)
    s.put(f"{API}/company", json={"description": "TEST desc"})
    assert cur(s) == ("salon", False)
    for b in s.get(f"{API}/branches").json():
        s.put(f"{API}/branches/{b['id']}", json={**b, "address": "Zona 1"})
    assert cur(s) == ("rules", False)
    assert s.post(f"{API}/salon-rules/reviewed").status_code == 200
    assert cur(s) == (None, True)


# Demo company unaffected
def test_bellavida_complete():
    t = requests.post(f"{API}/auth/login", json={"email": "admin@bellavida.com", "password": "Demo2026!"}).json()["token"]
    h = {"Authorization": f"Bearer {t}"}
    d = requests.get(f"{API}/onboarding", headers=h).json()
    assert d["setup_complete"] is True and d["current"] is None
