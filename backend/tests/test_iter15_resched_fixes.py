# Iteration 15: reschedule fixes - open_weekdays, allowed by status, others data for grouping, regression run of reschedule
import sys, uuid, pytest, requests
sys.path.insert(0, "/app/backend/tests")
from test_iter14_resched_calendar import book, mint, next_weekday, db, API, SLUG, CID, CARLA, BRANCH

PHONE = "+50255015501"


@pytest.fixture(scope="module")
def ctx():
    a = book(PHONE, next_weekday(5), "10:00")
    b = book(PHONE, next_weekday(6), "14:00")
    c = book(PHONE, next_weekday(7), "11:00")
    yield {"a": a, "b": b, "c": c, "h": {"X-Client-Token": mint(PHONE)}}
    db.appointments.delete_many({"client_name": {"$regex": "^TEST_Resched"}})
    db.clients.delete_many({"name": {"$regex": "^TEST_Resched"}})
    db.blocks.delete_many({"reason": "TEST_resched_block15"})


def url(aid):
    return f"{API}/public/salon/{SLUG}/appointments/{aid}/slots"


class TestIter15:
    def test_open_weekdays_zona10(self, ctx):
        d = requests.get(url(ctx["a"]["id"]), headers=ctx["h"]).json()
        assert d["open_weekdays"] == [0, 1, 2, 3, 4, 5]  # Sunday(6) closed
        assert d["allowed"] is True

    def test_cancelled_not_allowed(self, ctx):
        db.appointments.update_one({"id": ctx["b"]["id"]}, {"$set": {"status": "cancelled"}})
        d = requests.get(url(ctx["b"]["id"]), headers=ctx["h"]).json()
        assert d["allowed"] is False

    def test_completed_not_allowed(self, ctx):
        db.appointments.update_one({"id": ctx["c"]["id"]}, {"$set": {"status": "completed"}})
        d = requests.get(url(ctx["c"]["id"]), headers=ctx["h"]).json()
        assert d["allowed"] is False

    def test_confirmed_allowed(self, ctx):
        db.appointments.update_one({"id": ctx["c"]["id"]}, {"$set": {"status": "confirmed"}})
        d = requests.get(url(ctx["c"]["id"]), headers=ctx["h"]).json()
        assert d["allowed"] is True

    def test_others_have_ids_and_names(self, ctx):
        d2 = next_weekday(9)
        db.blocks.insert_one({"id": uuid.uuid4().hex[:12], "company_id": CID, "stylist_id": CARLA, "start_date": d2, "end_date": d2,
                              "reason": "TEST_resched_block15"})
        d = requests.get(url(ctx["a"]["id"]), headers=ctx["h"], params={"date": d2}).json()
        assert d["own"] == [] and d["others"]
        ids = {}
        for s in d["others"]:
            ids.setdefault(s["stylist_id"], set()).add(s["stylist_name"])
        assert all(len(v) == 1 for v in ids.values())  # one name per stylist id
        assert len(ids) >= 2

    def test_reschedule_regression(self, ctx):
        nd = next_weekday(10)
        own = requests.get(url(ctx["a"]["id"]), headers=ctx["h"], params={"date": nd}).json()["own"]
        assert own
        r = requests.post(f"{API}/public/salon/{SLUG}/appointments/{ctx['a']['id']}", headers=ctx["h"],
                          json={"action": "reschedule", "date": nd, "time": own[0]["time"], "stylist_id": own[0]["stylist_id"]})
        assert r.status_code == 200, r.text
        a = db.appointments.find_one({"id": ctx["a"]["id"]})
        assert a["date"] == nd and a["reschedule_count"] == 1
