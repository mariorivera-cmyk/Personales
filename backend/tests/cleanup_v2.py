"""Cleanup helper for iteration-2 UI/API test data (TEST_ prefixed)."""
from pymongo import MongoClient
from dotenv import dotenv_values

e = dotenv_values("/app/backend/.env")
db = MongoClient(e["MONGO_URL"])[e["DB_NAME"]]
bv = db.companies.find_one({"slug": "bellavida"})["id"]
appts = list(db.appointments.find({"company_id": bv, "client_name": {"$regex": "^TEST_"}}, {"id": 1, "client_phone": 1, "sale_id": 1}))
ids = [a["id"] for a in appts]
phones = list({a["client_phone"] for a in appts} | {c["phone"] for c in db.clients.find({"company_id": bv, "name": {"$regex": "^TEST_"}})})
print("appts", len(ids), "phones", phones)
print("sales", db.sales.delete_many({"$or": [{"appointment_id": {"$in": ids}}, {"client_name": {"$regex": "^TEST_"}}]}).deleted_count)
print("reviews", db.reviews.delete_many({"appointment_id": {"$in": ids}}).deleted_count)
db.appointments.delete_many({"id": {"$in": ids}})
for col in ("wa_messages", "otp_codes", "otp_locks", "data_requests", "email_outbox"):
    db[col].delete_many({"phone": {"$in": phones}})
db.clients.delete_many({"company_id": bv, "phone": {"$in": phones}})
db.otp_codes.delete_many({"phone": "+50250006666"})
db.otp_locks.delete_many({"phone": "+50250006666"})
db.wa_messages.delete_many({"phone": "+50250006666", "kind": "otp"})
db.notifications.delete_many({"company_id": bv, "$or": [{"text": {"$regex": "TEST_"}}] + [{"text": {"$regex": p.replace("+", "\\+")}} for p in phones]})
db.audit.delete_many({"company_id": bv, "detail": {"$regex": "TEST"}})
for c in db.companies.find({"name": {"$regex": "^TEST_"}}):
    for col in db.list_collection_names():
        if col != "companies":
            db[col].delete_many({"company_id": c["id"]})
    db.companies.delete_one({"id": c["id"]})
    print("deleted company", c["slug"])
db.users.delete_many({"email": {"$regex": "^test_"}})
print("left appts", db.appointments.count_documents({"client_name": {"$regex": "^TEST_"}}),
      "companies", db.companies.count_documents({"name": {"$regex": "^TEST_"}}),
      "products", db.products.count_documents({"name": {"$regex": "^TEST_"}}),
      "reviews", db.reviews.count_documents({"company_id": bv}), "gallery", db.gallery.count_documents({"company_id": bv}))
