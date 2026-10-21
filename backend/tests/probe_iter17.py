# Iteration 17 probes: coupon uses on failed checkout, partial package PUT, addon+package+membership, deposit+package
import sys
sys.path.insert(0, "/app/backend/tests")
from test_iter17_packages import *  # noqa

c = db.loyalty_coupons.find_one({"code": "BIENVENIDA10"})
u0 = c.get("uses", 0)
cl = requests.post(f"{API}/clients", headers=OWNER, json={"phone": PHONE, "name": "TEST_Pkg Probe"}).json()
cl = cl.get("client", cl)
a = make_appt(TRAT, PHONE, days=9)
r = requests.post(f"{API}/appointments/{a['id']}/checkout", headers=OWNER, json={"coupon_code": "BIENVENIDA10", "payments": [{"method": "cash", "amount": 1}]})
print("failed checkout", r.status_code, r.json())
print("coupon uses before/after failed checkout:", u0, db.loyalty_coupons.find_one({"code": "BIENVENIDA10"}).get("uses", 0))

p = requests.post(f"{API}/packages", headers=OWNER, json={**GOOD, "name": "TEST_Probe"}).json()
r = requests.put(f"{API}/packages/{p['id']}", headers=OWNER, json={"active": False})
print("partial PUT active=False:", r.status_code, r.text[:120])
r = requests.put(f"{API}/packages/nonexistent", headers=OWNER, json=GOOD)
print("PUT nonexistent:", r.status_code, r.text[:80])

# deposit + package
cp = requests.post(f"{API}/client-packages", headers=OWNER, json={"client_id": cl["id"], "package_id": p["id"], "branch_id": BRANCH,
                                                                  "payments": [{"method": "cash", "amount": 300}]}).json()
db.appointments.update_one({"id": a["id"]}, {"$set": {"deposit_paid": 50, "deposit_required": 50, "deposit_status": "received"}})
r = requests.post(f"{API}/appointments/{a['id']}/checkout", headers=OWNER, json={"package_id": cp["id"], "payments": []})
print("deposit+package:", r.status_code, {k: r.json().get(k) for k in ("total", "net", "deposit_applied", "package_cover")})

# addon + package + membership
db.clients.update_one({"id": cl["id"]}, {"$set": {"membership": "Oro"}})
a2 = make_appt(TRAT, PHONE, days=10)
db.appointments.update_one({"id": a2["id"]}, {"$set": {"price": 300, "addon_names": ["Mascarilla"], "addon_ids": []}})
o = requests.get(f"{API}/appointments/{a2['id']}/checkout-options", headers=OWNER).json()
print("options", o)
r = requests.post(f"{API}/appointments/{a2['id']}/checkout", headers=OWNER, json={"package_id": cp["id"], "apply_membership": True,
                                                                                 "payments": [{"method": "cash", "amount": 108}]})
print("addon+pkg+membership:", r.status_code, {k: r.json().get(k) for k in ("total", "promo", "package_cover", "commission")} if r.status_code == 200 else r.text)
# inactive package sale
requests.put(f"{API}/packages/{p['id']}", headers=OWNER, json={**GOOD, "name": "TEST_Probe", "active": False})
r = requests.post(f"{API}/client-packages", headers=OWNER, json={"client_id": cl["id"], "package_id": p["id"], "branch_id": BRANCH, "payments": [{"method": "cash", "amount": 300}]})
print("sell inactive:", r.status_code)

# cleanup
cps = list(db.client_packages.find({"client_phone": PHONE}))
db.sales.delete_many({"id": {"$in": [x["sale_id"] for x in cps]}})
db.client_packages.delete_many({"client_phone": PHONE})
db.packages.delete_many({"name": {"$regex": "^TEST_"}, "company_id": CID})
aids = [x["id"] for x in db.appointments.find({"client_phone": PHONE})]
db.sales.delete_many({"appointment_id": {"$in": aids}})
db.appointments.delete_many({"id": {"$in": aids}})
db.clients.delete_many({"phone": PHONE, "company_id": CID})
db.wa_messages.delete_many({"phone": PHONE})
db.loyalty_coupons.update_one({"code": "BIENVENIDA10"}, {"$unset": {"uses": ""}})
print("cleanup ok")
