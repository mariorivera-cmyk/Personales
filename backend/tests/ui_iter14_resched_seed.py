# UI seed for iteration 14: two TEST_ portal appointments for one phone (one reschedulable, one with max reschedules) + client token
import os, json, sys
sys.path.insert(0, "/app/backend/tests")
from test_iter14_resched_calendar import book, mint, next_weekday, db
PHONE = "+50255014409"
a1 = book(PHONE, next_weekday(4), "10:00")
a2 = book(PHONE, next_weekday(5), "14:00")
db.appointments.update_one({"id": a2["id"]}, {"$set": {"reschedule_count": 2}})
print(json.dumps({"a1": a1["id"], "a1_date": a1["date"], "a1_time": a1["time"], "a1_stylist": a1["stylist_id"], "a2": a2["id"], "token": mint(PHONE)}))
