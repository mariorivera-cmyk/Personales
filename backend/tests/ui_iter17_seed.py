# Iteration 17 UI seed: TEST clients + past appointments for checkout UI. Run with "clean" arg to remove.
import sys, json
sys.path.insert(0, "/app/backend/tests")
from test_iter17_packages import requests, API, OWNER, db, CID, TRAT, make_appt

P1, P2 = "+50255017711", "+50255017712"
if len(sys.argv) > 1 and sys.argv[1] == "clean":
    ph = [P1, P2]
    cps = list(db.client_packages.find({"client_phone": {"$in": ph}}))
    db.sales.delete_many({"id": {"$in": [x["sale_id"] for x in cps]}})
    db.client_packages.delete_many({"client_phone": {"$in": ph}})
    db.packages.delete_many({"company_id": CID, "name": {"$regex": "^TEST_"}})
    aids = [x["id"] for x in db.appointments.find({"client_phone": {"$in": ph}})]
    db.sales.delete_many({"appointment_id": {"$in": aids}})
    db.appointments.delete_many({"id": {"$in": aids}})
    db.clients.delete_many({"company_id": CID, "phone": {"$in": ph}})
    db.wa_messages.delete_many({"phone": {"$in": ph}})
    db.otp_codes.delete_many({"phone": {"$in": ph}})
    db.loyalty_coupons.update_one({"code": "BIENVENIDA10"}, {"$unset": {"uses": ""}})
    print("cleaned", db.packages.count_documents({"name": {"$regex": "^TEST_"}}), db.client_packages.count_documents({}))
    sys.exit()
out = {}
for k, ph, nm in (("c1", P1, "TEST_UI Pkg"), ("c2", P2, "TEST_UI Cupon")):
    c = requests.post(f"{API}/clients", headers=OWNER, json={"phone": ph, "name": nm}).json()
    out[k] = c.get("client", c)["id"]
out["a1"] = make_appt(TRAT, P1, days=3, name="TEST_UI Pkg")["id"]
out["a2"] = make_appt(TRAT, P2, days=4, name="TEST_UI Cupon")["id"]
out["date"] = db.appointments.find_one({"id": out["a1"]})["date"]
print(json.dumps(out))
