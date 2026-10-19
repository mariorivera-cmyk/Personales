# UI seed for iteration 15: reschedulable appt, max-reached appt, all Zona10 stylists blocked 2026-10-31 (forces next_days -> November)
import json, sys, uuid
sys.path.insert(0, "/app/backend/tests")
from test_iter14_resched_calendar import book, mint, next_weekday, db, CID
PHONE = "+50255015509"
a1 = book(PHONE, next_weekday(4), "10:00")
a2 = book(PHONE, next_weekday(5), "14:00")
db.appointments.update_one({"id": a2["id"]}, {"$set": {"reschedule_count": 2}})
for st in ["a14fc0cc74ec", "6a6b2dbb5ee9", "b0c4323f1d59"]:
    db.blocks.insert_one({"id": uuid.uuid4().hex[:12], "company_id": CID, "stylist_id": st, "start_date": "2026-10-31", "end_date": "2026-10-31", "reason": "TEST_resched_block15"})
# Carla blocked on 2026-10-29 -> others grouping
db.blocks.insert_one({"id": uuid.uuid4().hex[:12], "company_id": CID, "stylist_id": "a14fc0cc74ec", "start_date": "2026-10-29", "end_date": "2026-10-29", "reason": "TEST_resched_block15"})
print(json.dumps({"a1": a1["id"], "a1_date": a1["date"], "a1_time": a1["time"], "a2": a2["id"], "token": mint(PHONE)}))
