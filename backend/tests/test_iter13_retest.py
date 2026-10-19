# Iteration 13 retest: onboarding pending for complete company + skip flow wording basics
import os, requests
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"

def tok(e, p):
    r = requests.post(f"{API}/auth/login", json={"email": e, "password": p}); assert r.status_code == 200
    return {"Authorization": "Bearer " + r.json()["token"]}

# Complete company -> pending must be empty
def test_bellavida_onboarding_pending_empty():
    r = requests.get(f"{API}/onboarding", headers=tok("admin@bellavida.com", "Demo2026!"))
    assert r.status_code == 200
    d = r.json()
    assert d["setup_complete"] is True
    assert d["pending"] == []
    assert d["current"] is None
