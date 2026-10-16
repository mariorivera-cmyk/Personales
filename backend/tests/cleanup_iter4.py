"""Cleanup TEST_ data created in iteration 4 (D1-D10) on bellavida + signup test companies; resets bellavida rules."""
import requests
from pymongo import MongoClient
from dotenv import dotenv_values

API = [l.split("=", 1)[1].strip() for l in open("/app/frontend/.env") if l.startswith("REACT_APP_BACKEND_URL")][0].rstrip("/") + "/api"
E = dotenv_values("/app/backend/.env")
db = MongoClient(E["MONGO_URL"])[E["DB_NAME"]]
CID = db.companies.find_one({"slug": "bellavida"})["id"]
clients = list(db.clients.find({"company_id": CID, "name": {"$regex": "^TEST_"}}))
phones = [c["phone"] for c in clients]
appts = [a["id"] for a in db.appointments.find({"company_id": CID, "$or": [{"client_name": {"$regex": "^TEST_"}}, {"client_phone": {"$in": phones}}]})]
prods = [p["id"] for p in db.products.find({"company_id": CID, "name": {"$regex": "^TEST_"}})]
print("appts", db.appointments.delete_many({"id": {"$in": appts}}).deleted_count)
print("sales", db.sales.delete_many({"company_id": CID, "$or": [{"appointment_id": {"$in": appts}}, {"items.product_id": {"$in": prods}}, {"client_name": {"$regex": "^TEST_"}}]}).deleted_count)
print("products", db.products.delete_many({"id": {"$in": prods}}).deleted_count, db.inventory_moves.delete_many({"product_id": {"$in": prods}}).deleted_count)
for col, q in (("wa_messages", {"phone": {"$in": phones}}), ("otp_codes", {"phone": {"$in": phones}}), ("otp_locks", {"phone": {"$in": phones}}),
               ("waitlist", {"client_phone": {"$in": phones}}), ("clients", {"id": {"$in": [c["id"] for c in clients]}}),
               ("notifications", {"company_id": CID, "text": {"$regex": "TEST_"}})):
    print(col, db[col].delete_many(q).deleted_count)
for co in db.companies.find({"name": {"$regex": "^TEST_"}}):
    for col in ("users", "services", "branches", "stylists", "invoices", "payments", "notifications", "company_history", "audit_logs", "plan_history"):
        db[col].delete_many({"company_id": co["id"]})
    db.companies.delete_one({"id": co["id"]})
    print("company deleted", co["slug"])
H = {"Authorization": "Bearer " + requests.post(f"{API}/auth/login", json={"email": "admin@bellavida.com", "password": "Demo2026!"}).json()["token"]}
print("reset", requests.post(f"{API}/salon-rules/reset", json={}, headers=H).status_code)
