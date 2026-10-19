# Iteration 14: portal reschedule calendar - GET /public/salon/{slug}/appointments/{aid}/slots + reschedule POST
import os, re, uuid, jwt, pytest, requests
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
SLUG = "bellavida"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
CO = db.companies.find_one({"slug": SLUG})
CID = CO["id"]
BRANCH = "9c211150faac"   # Zona 10 (closed Sunday)
SERVICE = "81a40e910fdd"  # Tratamiento capilar 30m (any stylist)
CARLA = "a14fc0cc74ec"
PHONE_A = "+50255014401"
PHONE_B = "+50255014402"


def next_weekday(days_ahead, wd=None):
    d = datetime.now() + timedelta(days=days_ahead)
    while (wd is None and d.weekday() == 6) or (wd is not None and d.weekday() != wd) or d.strftime("%Y-%m-%d") in CO["settings"].get("holidays", []):
        d += timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def mint(phone):
    return jwt.encode({"sub": phone, "cid": CID, "type": "client", "exp": datetime.now(timezone.utc) + timedelta(minutes=30)},
                      os.environ["JWT_SECRET"], algorithm="HS256")


def book(phone, date, time, stylist=CARLA):
    sl = requests.get(f"{API}/public/salon/{SLUG}/slots", params={"branch_id": BRANCH, "service_id": SERVICE, "date": date, "stylist_id": stylist}).json()["slots"]
    times = [s["time"] for s in sl]
    assert times, "no free slots for Carla"
    time = time if time in times else times[len(times) // 3]
    r = requests.post(f"{API}/public/salon/{SLUG}/book", json={"branch_id": BRANCH, "service_id": SERVICE, "date": date, "time": time,
                                                               "phone": phone, "name": "TEST_Resched " + phone[-2:], "stylist_id": stylist})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def ctx():
    date = next_weekday(5)
    a = book(PHONE_A, date, "10:00")
    b = book(PHONE_B, date, "15:00")
    # OTP flow for phone A (real verification)
    r = requests.post(f"{API}/public/salon/{SLUG}/otp", json={"phone": PHONE_A})
    tok = None
    if r.status_code == 200:
        msg = db.wa_messages.find_one({"company_id": CID, "phone": PHONE_A, "kind": "otp"}, sort=[("created_at", -1)])
        code = re.search(r"\b(\d{6})\b", msg["text"] if "text" in msg else str(msg)).group(1)
        v = requests.post(f"{API}/public/salon/{SLUG}/otp/verify", json={"phone": PHONE_A, "code": code})
        if v.status_code == 200:
            tok = v.json()["token"]
    tok = tok or mint(PHONE_A)
    yield {"date": date, "a": a, "b": b, "hA": {"X-Client-Token": tok}, "hB": {"X-Client-Token": mint(PHONE_B)}}
    db.appointments.delete_many({"client_name": {"$regex": "^TEST_Resched"}})
    db.clients.delete_many({"name": {"$regex": "^TEST_Resched"}})
    db.blocks.delete_many({"reason": "TEST_resched_block"})


def url(aid):
    return f"{API}/public/salon/{SLUG}/appointments/{aid}/slots"


class TestReschedSlots:
    def test_no_token_401(self, ctx):
        r = requests.get(url(ctx["a"]["id"]))
        assert r.status_code == 401

    def test_other_client_404(self, ctx):
        r = requests.get(url(ctx["a"]["id"]), headers=ctx["hB"])
        assert r.status_code == 404

    def test_info_without_date(self, ctx):
        r = requests.get(url(ctx["a"]["id"]), headers=ctx["hA"])
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["allowed"] is True and d["count"] == 0
        assert d["reschedule_hours"] == 12 and d["max_reschedules"] == 2
        assert d["stylist_name"] == "Carla Méndez"
        assert len(d["min_date"]) == 10 and d["max_date"] >= d["min_date"]
        assert isinstance(d["holidays"], list)
        assert "own" not in d

    def test_own_slots_include_self(self, ctx):
        r = requests.get(url(ctx["a"]["id"]), headers=ctx["hA"], params={"date": ctx["date"]})
        d = r.json()
        assert r.status_code == 200 and d["date"] == ctx["date"]
        times = [s["time"] for s in d["own"]]
        assert ctx["a"]["time"] in times, times
        assert all(s["stylist_id"] == CARLA for s in d["own"])
        assert d["others"] == [] and d["next_days"] == []

    def test_others_when_stylist_blocked(self, ctx):
        d2 = next_weekday(8)
        db.blocks.insert_one({"id": uuid.uuid4().hex[:12], "company_id": CID, "stylist_id": CARLA, "start_date": d2, "end_date": d2,
                              "reason": "TEST_resched_block"})
        r = requests.get(url(ctx["a"]["id"]), headers=ctx["hA"], params={"date": d2})
        d = r.json()
        assert d["own"] == []
        assert len(d["others"]) > 0 and all(s["stylist_id"] != CARLA for s in d["others"])
        assert all(s.get("stylist_name") for s in d["others"])

    def test_no_slots_sunday_next_days(self, ctx):
        sun = next_weekday(3, wd=6)
        r = requests.get(url(ctx["a"]["id"]), headers=ctx["hA"], params={"date": sun})
        d = r.json()
        assert d["own"] == [] and d["others"] == []
        assert 1 <= len(d["next_days"]) <= 3
        assert all(n["date"] > sun and n["count"] > 0 for n in d["next_days"])

    def test_holiday_no_slots(self, ctx):
        r = requests.get(url(ctx["a"]["id"]), headers=ctx["hA"], params={"date": "2026-12-25"})
        d = r.json()
        assert d["own"] == [] and d["others"] == []

    def test_reschedule_and_verify(self, ctx):
        nd = next_weekday(6)
        slots = requests.get(url(ctx["a"]["id"]), headers=ctx["hA"], params={"date": nd}).json()["own"]
        pick = [s for s in slots if s["time"] == "11:00"] or slots
        r = requests.post(f"{API}/public/salon/{SLUG}/appointments/{ctx['a']['id']}", headers=ctx["hA"],
                          json={"action": "reschedule", "date": nd, "time": pick[0]["time"], "stylist_id": pick[0]["stylist_id"]})
        assert r.status_code == 200, r.text
        a = db.appointments.find_one({"id": ctx["a"]["id"]})
        assert a["date"] == nd and a["time"] == pick[0]["time"] and a["reschedule_count"] == 1
        info = requests.get(url(ctx["a"]["id"]), headers=ctx["hA"]).json()
        assert info["count"] == 1 and info["allowed"] is True

    def test_reschedule_to_other_stylist(self, ctx):
        d2 = next_weekday(8)
        others = requests.get(url(ctx["a"]["id"]), headers=ctx["hA"], params={"date": d2}).json()["others"]
        s = others[0]
        r = requests.post(f"{API}/public/salon/{SLUG}/appointments/{ctx['a']['id']}", headers=ctx["hA"],
                          json={"action": "reschedule", "date": d2, "time": s["time"], "stylist_id": s["stylist_id"]})
        assert r.status_code == 200, r.text
        a = db.appointments.find_one({"id": ctx["a"]["id"]})
        assert a["stylist_id"] == s["stylist_id"] and a["reschedule_count"] == 2

    def test_max_reached_not_allowed(self, ctx):
        info = requests.get(url(ctx["a"]["id"]), headers=ctx["hA"]).json()
        assert info["allowed"] is False and info["count"] == 2
        r = requests.post(f"{API}/public/salon/{SLUG}/appointments/{ctx['a']['id']}", headers=ctx["hA"],
                          json={"action": "reschedule", "date": next_weekday(10), "time": "10:00"})
        assert r.status_code == 409

    def test_within_hours_not_allowed(self, ctx):
        soon = datetime.now() + timedelta(hours=5)  # server local tz may differ; force by DB
        db.appointments.update_one({"id": ctx["b"]["id"]}, {"$set": {"date": (datetime.utcnow() - timedelta(hours=6) + timedelta(hours=4)).strftime("%Y-%m-%d"),
                                                                      "time": (datetime.utcnow() - timedelta(hours=6) + timedelta(hours=4)).strftime("%H:00")}})
        info = requests.get(url(ctx["b"]["id"]), headers=ctx["hB"]).json()
        assert info["allowed"] is False and info["count"] == 0
