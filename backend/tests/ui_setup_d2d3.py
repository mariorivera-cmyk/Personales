"""Helper: create TEST appts for UI tests of D2/D3. Prints ids as JSON."""
import json, uuid, requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pymongo import MongoClient
from dotenv import dotenv_values

BASE = [l.split("=", 1)[1].strip() for l in open("/app/frontend/.env") if l.startswith("REACT_APP_BACKEND_URL")][0].rstrip("/")
API = BASE + "/api"
E = dotenv_values("/app/backend/.env")
mdb = MongoClient(E["MONGO_URL"])[E["DB_NAME"]]
H = {"Authorization": "Bearer " + requests.post(f"{API}/auth/login", json={"email": "admin@bellavida.com", "password": "Demo2026!"}).json()["token"]}
ZONA10, CORTE, BALAYAGE = "9c211150faac", "c41db866d7a8", "c7ac7bc8bee5"
now = datetime.now(ZoneInfo("America/Guatemala"))
d1 = now + timedelta(days=1)
while d1.weekday() == 6:
    d1 += timedelta(days=1)
d1 = d1.strftime("%Y-%m-%d")


def book(svc, date, idx=0):
    p = "+5024" + str(uuid.uuid4().int)[:7]
    sl = requests.get(f"{API}/public/salon/bellavida/slots", params={"branch_id": ZONA10, "service_id": svc, "date": date}).json()["slots"]
    r = requests.post(f"{API}/appointments", json={"branch_id": ZONA10, "service_id": svc, "date": date, "time": sl[idx]["time"], "phone": p, "name": "TEST_UI Cli"}, headers=H)
    r.raise_for_status()
    return r.json()


late = book(BALAYAGE, d1, 0)
requests.post(f"{API}/appointments/{late['id']}/deposit", json={}, headers=H).raise_for_status()
past = book(CORTE, d1, 3)
td = now.strftime("%Y-%m-%d")
mdb.appointments.update_one({"id": past["id"]}, {"$set": {"date": td, "time": "08:00", "end_time": "08:45"}})
print(json.dumps({"late": late["id"], "late_client": late["client_id"], "past": past["id"], "d1": d1, "today": td, "late_time": late["time"]}))
