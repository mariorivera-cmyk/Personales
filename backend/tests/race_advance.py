# Ad-hoc: concurrent double advance-charge race check
import sys, threading
sys.path.insert(0, "/app/backend/tests")
import test_advance_charge as t

sa = t.login("mario.rivera@gmail.com", "Admin2026!")
c = t.mk(sa, next_billing_date=t.D(10))
res = []
def go():
    res.append(t.requests.post(t.url(c["id"]), headers=sa, json={"confirm": True}).status_code)
ths = [threading.Thread(target=go) for _ in range(3)]
[x.start() for x in ths]; [x.join() for x in ths]
print("statuses", res, "paid advance invoices", t.mdb.invoices.count_documents({"company_id": c["id"], "kind": "advance", "status": "paid"}),
      "nbd", t.co(c["id"])["next_billing_date"])
t.requests.delete(f"{t.BASE_URL}/api/admin/companies/{c['id']}", headers=sa, json={"confirm": "ELIMINAR"})
t.mdb.invoices.delete_many({"company_id": c["id"]}); t.mdb.payments.delete_many({"company_id": c["id"]})
print("leftover TEST_Adv:", t.mdb.companies.count_documents({"name": {"$regex": "^TEST_Adv"}}))
