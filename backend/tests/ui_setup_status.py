# Helper: creates TEST_ company for UI test and checks WA inbound when paused
import sys
import requests
from test_company_status_delete import BASE_URL, login, PW

sa = {"Authorization": f"Bearer {login('mario.rivera@gmail.com', 'Admin2026!').json()['token']}"}
plan = requests.get(f"{BASE_URL}/api/admin/plans", headers=sa).json()[0]["id"]
mode = sys.argv[1]
if mode == "wa":
    body = {"company_name": "TEST_Co WA", "slug": "test-co-wa", "email": "test_co_wa@example.com", "password": PW, "plan_id": plan,
            "whatsapp_number": "+50299112233", "status": "active", "modules": ["whatsapp", "portal"]}
    c = requests.post(f"{BASE_URL}/api/admin/companies", headers=sa, json=body).json()
    requests.post(f"{BASE_URL}/api/admin/companies/{c['id']}/status", headers=sa, json={"status": "paused"})
    r = requests.post(f"{BASE_URL}/api/wa/inbound", json={"to": "+50299112233", "from_phone": "+50211112222", "text": "hola"})
    print("WA paused inbound:", r.status_code, r.text)
    print(requests.delete(f"{BASE_URL}/api/admin/companies/{c['id']}", headers=sa, json={"confirm": "ELIMINAR"}).text)
else:
    body = {"company_name": "TEST_Co UI", "slug": "test-co-ui", "email": "test_co_ui@example.com", "password": PW, "plan_id": plan,
            "whatsapp_number": "+50299445566", "status": "active"}
    r = requests.post(f"{BASE_URL}/api/admin/companies", headers=sa, json=body)
    print(r.status_code, r.json().get("id"), r.json().get("slug"))
