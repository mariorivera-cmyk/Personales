# Iteration 18 UI seed: client w/ membership + package, 2 past appts (one with deposit). "clean" arg removes.
import sys, json
sys.path.insert(0, "/app/backend/tests")
from test_iter18_fixes import requests, API, OWNER, db, CID, TRAT, BRANCH, make_appt, PHONE

if len(sys.argv) > 1 and sys.argv[1] == "clean":
    cps = list(db.client_packages.find({"client_phone": PHONE}))
    db.sales.delete_many({"id": {"$in": [x["sale_id"] for x in cps]}})
    db.client_packages.delete_many({"client_phone": PHONE})
    db.packages.delete_many({"company_id": CID, "name": {"$regex": "^TEST_It18"}})
    aids = [x["id"] for x in db.appointments.find({"client_phone": PHONE})]
    db.sales.delete_many({"appointment_id": {"$in": aids}})
    db.appointments.delete_many({"id": {"$in": aids}})
    db.clients.delete_many({"company_id": CID, "phone": PHONE})
    db.wa_messages.delete_many({"phone": PHONE})
    db.notifications.delete_many({"company_id": CID, "text": {"$regex": "TEST_It18"}})
    db.loyalty_coupons.update_one({"code": "BIENVENIDA10", "company_id": CID}, {"$unset": {"uses": ""}})
    print("cleaned")
    sys.exit()
c = requests.post(f"{API}/clients", headers=OWNER, json={"phone": PHONE, "name": "TEST_It18 Client"}).json()
cl = c.get("client", c)
db.clients.update_one({"id": cl["id"]}, {"$set": {"membership": "oro"}})
pk = requests.post(f"{API}/packages", headers=OWNER, json={"name": "TEST_It18 Pack", "items": [{"service_id": TRAT, "qty": 3}], "price": 450, "validity_days": 30, "active": True}).json()
cp = requests.post(f"{API}/client-packages", headers=OWNER, json={"client_id": cl["id"], "package_id": pk["id"], "branch_id": BRANCH, "payments": [{"method": "cash", "amount": 450}]}).json()
a1 = make_appt(TRAT, 3, deposit=50)
a2 = make_appt(TRAT, 4)
db.appointments.update_one({"id": a1["id"]}, {"$set": {"time": "07:00"}})
db.appointments.update_one({"id": a2["id"]}, {"$set": {"time": "19:00"}})
print(json.dumps({"client": cl["id"], "cp": cp["id"], "a1": a1["id"], "a2": a2["id"], "date": a1["date"]}))
