# Seed bellavida appointments (far >24h with deposit received, late <24h) for portal cancel-policy UI test
import os, time, datetime as dt, requests, json
from pymongo import MongoClient
from pathlib import Path
ENV = dict(l.split("=", 1) for l in Path("/app/backend/.env").read_text().splitlines() if "=" in l)
db = MongoClient(ENV["MONGO_URL"].strip('"'))[ENV["DB_NAME"].strip('"')]
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
st = str(int(time.time()))
PHONE = f"+5025{st[-7:]}"
s = requests.Session()
s.headers["Authorization"] = "Bearer " + requests.post(f"{API}/auth/login", json={"email": "admin@bellavida.com", "password": "Demo2026!"}).json()["token"]
pub = requests.get(f"{API}/public/salon/bellavida").json()
br, svc = pub["branches"][0]["id"], pub["services"][0]["id"]
out = {"phone": PHONE}
for name, off, early in (("far", 4, False), ("late", 1, True)):
    date = (dt.date.today() + dt.timedelta(days=off)).isoformat()
    slots = requests.get(f"{API}/public/salon/bellavida/slots", params={"branch_id": br, "service_id": svc, "date": date}).json()["slots"]
    sl = slots[0] if early else slots[-1]
    r = s.post(f"{API}/appointments", json={"branch_id": br, "service_id": svc, "date": date, "time": sl["time"], "phone": PHONE,
                                           "name": "TEST_Portal UI", "stylist_id": sl.get("stylist_id")})
    out[name] = r.json()["id"]
db.appointments.update_one({"id": out["far"]}, {"$set": {"deposit_status": "received", "deposit_paid": 50.0, "deposit_required": 50.0}})
print(json.dumps(out))
