# Cleanup iteration 13 TEST_ data: TEST_ui12 companies and TEST_Portal UI appointments on bellavida
import os, requests
from pymongo import MongoClient
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
h = {"Authorization": "Bearer " + requests.post(f"{API}/auth/login", json={"email": "mario.rivera@gmail.com", "password": "Admin2026!"}).json()["token"]}
cos = requests.get(f"{API}/admin/companies", headers=h).json()
cos = cos if isinstance(cos, list) else cos.get("items", [])
for c in cos:
    if (c.get("slug") or "").startswith(("test-ui12-", "test-skip")) and c.get("slug") not in ("salon-retest-trinity", "wwwpruebacom"):
        print("delete", c["slug"], requests.delete(f"{API}/admin/companies/{c['id']}", headers=h, json={"confirm": "ELIMINAR"}).status_code)
r = db.appointments.delete_many({"client_name": {"$regex": "^TEST_"}})
print("appts deleted", r.deleted_count, "clients", db.clients.delete_many({"name": {"$regex": "^TEST_"}}).deleted_count)
