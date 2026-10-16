# Ad-hoc: create/delete UI-test company. usage: python ui_adv_seed.py create|delete
import sys, json
sys.path.insert(0, "/app/backend/tests")
import test_advance_charge as t
sa = t.login("mario.rivera@gmail.com", "Admin2026!")
if sys.argv[1] == "create":
    a = t.mk(sa, next_billing_date=t.D(10))
    b = t.mk(sa, card="0002", next_billing_date=t.D(10))
    p = t.mk(sa)
    t.mdb.companies.update_one({"id": p["id"]}, {"$set": {"status": "paused"}})
    json.dump({"ok": a, "rej": b, "paused": p}, open("/tmp/ui_adv.json", "w"))
    print(a["slug"], b["slug"], p["slug"])
else:
    d = json.load(open("/tmp/ui_adv.json"))
    for c in d.values():
        t.requests.delete(f"{t.BASE_URL}/api/admin/companies/{c['id']}", headers=sa, json={"confirm": "ELIMINAR"})
        t.mdb.invoices.delete_many({"company_id": c["id"]}); t.mdb.payments.delete_many({"company_id": c["id"]})
    print("leftover", t.mdb.companies.count_documents({"name": {"$regex": "^TEST_Adv"}}))
