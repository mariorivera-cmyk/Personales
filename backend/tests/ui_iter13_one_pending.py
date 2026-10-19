# Bring TEST_ ui company to exactly 1 pending step (bank) in skipped mode
import os, sys, requests
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
s = requests.Session()
s.headers["Authorization"] = "Bearer " + requests.post(f"{API}/auth/login", json={"email": sys.argv[1], "password": "Test12345!"}).json()["token"]
s.post(f"{API}/onboarding", json={"skipped": True})
svc = s.post(f"{API}/services", json={"name": "TEST_Corte", "category": "Cabello", "duration": 30, "price": 50}).json()["id"]
s.put(f"{API}/company", json={"description": "Salón TEST"})
br = s.get(f"{API}/branches").json()
for b in br: s.put(f"{API}/branches/{b['id']}", json={**b, "address": "Zona 1"})
print(s.post(f"{API}/stylists", json={"name": "TEST_Est", "phone": "+50255551288", "service_ids": [svc], "branch_id": br[0]["id"]}).status_code)
s.put(f"{API}/salon-rules", json={"values": {"bank_name": "TEST_Banco"}})
print([p["key"] for p in s.get(f"{API}/onboarding").json()["pending"]])
