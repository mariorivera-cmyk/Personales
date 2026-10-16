"""Iteration 5: service categories CRUD + stylist service_ids availability filter."""
import uuid
import pytest
import requests

for line in open("/app/frontend/.env"):
    if line.startswith("REACT_APP_BACKEND_URL"):
        BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
API = f"{BASE_URL}/api"
SLUG = "bellavida"
ZONA10 = "9c211150faac"
DATE = "2026-10-19"  # Monday
RUN = uuid.uuid4().hex[:4]


def login(email):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": "Demo2026!"}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def A():
    return login("admin@bellavida.com")


@pytest.fixture(scope="module")
def created(A):
    c = {"cats": [], "services": [], "stylists": []}
    yield c
    for s in c["stylists"]:
        requests.delete(f"{API}/stylists/{s}", headers=A)
    for s in c["services"]:
        requests.delete(f"{API}/services/{s}", headers=A)
    for cat in requests.get(f"{API}/service-categories", headers=A).json():
        if cat["name"].lower().startswith("test_"):
            requests.delete(f"{API}/service-categories/{cat['id']}", headers=A)


def cats(A):
    r = requests.get(f"{API}/service-categories", headers=A)
    assert r.status_code == 200, r.text
    return r.json()


# Categories: list/autoimport
def test_list_has_counts_and_autoimport(A):
    cs = cats(A)
    assert cs and all("services" in c and "_id" not in c for c in cs)
    svc_cats = {s.get("category") for s in requests.get(f"{API}/services", headers=A).json() if s.get("category")}
    assert svc_cats <= {c["name"] for c in cs}


# Categories: create + duplicate
def test_create_and_duplicate(A, created):
    n = f"TEST_Cat{RUN}"
    r = requests.post(f"{API}/service-categories", json={"name": n}, headers=A)
    assert r.status_code == 200, r.text
    assert r.json()["name"] == n
    created["cats"].append(r.json()["id"])
    assert any(c["name"] == n and c["services"] == 0 for c in cats(A))
    d = requests.post(f"{API}/service-categories", json={"name": n.lower()}, headers=A)
    assert d.status_code == 400 and "existe" in d.json()["detail"]
    e = requests.post(f"{API}/service-categories", json={"name": "  "}, headers=A)
    assert e.status_code == 400


# Receptionist forbidden
def test_receptionist_forbidden():
    R = login("recepcion@bellavida.com")
    r = requests.post(f"{API}/service-categories", json={"name": f"TEST_R{RUN}"}, headers=R)
    assert r.status_code == 403
    assert requests.get(f"{API}/service-categories", headers=R).status_code == 200


# Rename propagates to services; delete blocked when in use
def test_rename_propagates_and_delete_blocked(A, created):
    cid = created["cats"][0]
    old = f"TEST_Cat{RUN}"
    s = requests.post(f"{API}/services", json={"name": f"TEST_Svc{RUN}", "category": old, "duration": 30, "price": 100,
                                                "active": True, "stylist_ids": []}, headers=A).json()
    created["services"].append(s["id"])
    new = f"TEST_Ren{RUN}"
    r = requests.put(f"{API}/service-categories/{cid}", json={"name": new}, headers=A)
    assert r.status_code == 200, r.text
    svc = [x for x in requests.get(f"{API}/services", headers=A).json() if x["id"] == s["id"]][0]
    assert svc["category"] == new
    c = [x for x in cats(A) if x["id"] == cid][0]
    assert c["name"] == new and c["services"] == 1
    d = requests.delete(f"{API}/service-categories/{cid}", headers=A)
    assert d.status_code == 400 and "No se puede eliminar" in d.json()["detail"]


# Rename to existing name (case-insensitive) should be rejected
def test_rename_duplicate_case_insensitive(A, created):
    cid = created["cats"][0]
    other = requests.post(f"{API}/service-categories", json={"name": f"TEST_Other{RUN}"}, headers=A).json()
    exact = requests.put(f"{API}/service-categories/{cid}", json={"name": f"TEST_Other{RUN}"}, headers=A)
    assert exact.status_code == 400
    ci = requests.put(f"{API}/service-categories/{cid}", json={"name": f"test_other{RUN}"}, headers=A)
    assert ci.status_code == 400, f"case-insensitive dup rename allowed: {ci.status_code}"
    requests.delete(f"{API}/service-categories/{other['id']}", headers=A)


# Delete unused category
def test_delete_unused(A, created):
    r = requests.post(f"{API}/service-categories", json={"name": f"TEST_Del{RUN}"}, headers=A).json()
    d = requests.delete(f"{API}/service-categories/{r['id']}", headers=A)
    assert d.status_code == 200
    assert not any(c["id"] == r["id"] for c in cats(A))
    assert requests.delete(f"{API}/service-categories/{r['id']}", headers=A).status_code == 404


# Stylist service_ids filters availability
def test_stylist_service_ids_slots(A, created):
    s1 = requests.post(f"{API}/services", json={"name": f"TEST_S1{RUN}", "category": "", "duration": 30, "price": 50,
                                                 "active": True, "stylist_ids": []}, headers=A).json()
    s2 = requests.post(f"{API}/services", json={"name": f"TEST_S2{RUN}", "category": "", "duration": 30, "price": 50,
                                                 "active": True, "stylist_ids": []}, headers=A).json()
    created["services"] += [s1["id"], s2["id"]]
    st = requests.post(f"{API}/stylists", json={"name": f"TEST_Sty{RUN}", "branch_id": ZONA10, "active": True,
                                                 "service_ids": [s1["id"]]}, headers=A).json()
    created["stylists"].append(st["id"])
    assert st["service_ids"] == [s1["id"]]

    def ids(sid):
        r = requests.get(f"{API}/public/salon/{SLUG}/slots", params={"branch_id": ZONA10, "service_id": sid, "date": DATE})
        assert r.status_code == 200, r.text
        return {x["stylist_id"] for x in r.json()["slots"]}
    assert st["id"] in ids(s1["id"])
    assert st["id"] not in ids(s2["id"])
    # internal slots endpoint
    r = requests.get(f"{API}/slots", params={"branch_id": ZONA10, "service_id": s2["id"], "date": DATE}, headers=A)
    if r.status_code == 200:
        body = r.json()
        sl = body["slots"] if isinstance(body, dict) else body
        assert st["id"] not in {x["stylist_id"] for x in sl}
    # empty list -> all
    requests.put(f"{API}/stylists/{st['id']}", json={"service_ids": []}, headers=A)
    assert st["id"] in ids(s2["id"])


# Templates create missing categories
def test_templates_create_category(A, created):
    n = f"TEST_TplCat{RUN}"
    r = requests.post(f"{API}/service-templates", json={"items": [{"name": f"TEST_Tpl{RUN}", "category": n, "duration": 30, "price": 10}]}, headers=A)
    assert r.status_code == 200 and r.json()["created"] == 1
    svc = [x for x in requests.get(f"{API}/services", headers=A).json() if x["name"] == f"TEST_Tpl{RUN}"][0]
    created["services"].append(svc["id"])
    assert any(c["name"] == n for c in cats(A))
