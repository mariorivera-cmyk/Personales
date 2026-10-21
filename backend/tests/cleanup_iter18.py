# Iteration 18 cleanup: delete services created via templates since snapshot /tmp/it18_snap.json
import os, json, requests
from pymongo import MongoClient
from dotenv import load_dotenv
load_dotenv("/app/backend/.env"); load_dotenv("/app/frontend/.env")
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
cid = db.companies.find_one({"slug": "bellavida"})["id"]
snap = json.load(open("/tmp/it18_snap.json"))
t = requests.post(f"{API}/auth/login", json={"email": "admin@bellavida.com", "password": "Demo2026!"}).json()["token"]
for s in db.services.find({"company_id": cid, "id": {"$nin": snap["svc"]}}):
    print("delete", s["name"], requests.delete(f"{API}/services/{s['id']}", headers={"Authorization": f"Bearer {t}"}).status_code)
db.service_categories.delete_many({"company_id": cid, "id": {"$nin": snap["cat"]}})
