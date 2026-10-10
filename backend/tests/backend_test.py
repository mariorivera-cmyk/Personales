"""Backend regression tests for Salon SaaS platform.

Covers: auth, dashboard, agenda/availability/booking, CRM, waitlist, loyalty,
marketing, reports, admin SaaS flows, billing, suspension, role restrictions,
public portal, WhatsApp inbound (simulated).

Public URL comes from frontend/.env REACT_APP_BACKEND_URL.
"""
import os
import re
import uuid
import pytest
import requests

# Read public backend URL (same URL the frontend uses)
with open("/app/frontend/.env") as f:
    for line in f:
        if line.startswith("REACT_APP_BACKEND_URL"):
            BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")

API = f"{BASE_URL}/api"

TEST_DATE = "2026-10-12"  # Monday (Zona 10 closed on Sunday 2026-10-11)
TEST_DATE_SUNDAY = "2026-10-11"
SLUG = "bellavida"
WA_NUMBER = "+50255550001"

CREDS = {
    "super": ("mario.rivera@gmail.com", "Admin2026!"),
    "admin": ("admin@bellavida.com", "Demo2026!"),
    "manager": ("gerente@bellavida.com", "Demo2026!"),
    "reception": ("recepcion@bellavida.com", "Demo2026!"),
    "stylist": ("estilista@bellavida.com", "Demo2026!"),
}


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"Login failed for {email}: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="session")
def tokens():
    out = {}
    for key, (email, pw) in CREDS.items():
        out[key] = _login(email, pw)
    return out


def H(tokens, role, extra=None):
    h = {"Authorization": f"Bearer {tokens[role]['token']}"}
    if extra:
        h.update(extra)
    return h


# ============== Auth ==============
class TestAuth:
    def test_health(self):
        r = requests.get(f"{API}/health", timeout=10)
        assert r.status_code == 200

    def test_login_super(self):
        d = _login(*CREDS["super"])
        assert d["user"]["role"] == "super_admin"
        assert d["token"]

    def test_login_all_roles(self, tokens):
        assert tokens["admin"]["user"]["role"] == "company_admin"
        assert tokens["manager"]["user"]["role"] == "branch_manager"
        assert tokens["reception"]["user"]["role"] == "receptionist"
        assert tokens["stylist"]["user"]["role"] == "stylist"

    def test_login_invalid(self):
        r = requests.post(f"{API}/auth/login", json={"email": "admin@bellavida.com", "password": "wrong"})
        assert r.status_code in (400, 401, 403)

    def test_me(self, tokens):
        r = requests.get(f"{API}/auth/me", headers=H(tokens, "admin"))
        assert r.status_code == 200
        data = r.json()
        assert "user" in data and "company" in data
        assert data["company"]["slug"] == SLUG


# ============== Dashboard & basic company ==============
class TestDashboard:
    def test_dashboard(self, tokens):
        r = requests.get(f"{API}/dashboard", headers=H(tokens, "admin"))
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("today", "today_list", "future", "occupancy", "sales", "series"):
            assert k in data

    def test_company_get(self, tokens):
        r = requests.get(f"{API}/company", headers=H(tokens, "admin"))
        assert r.status_code == 200
        assert r.json()["slug"] == SLUG


# ============== Agenda / Availability / Booking ==============
@pytest.fixture(scope="session")
def company_ctx(tokens):
    h = H(tokens, "admin")
    branches = requests.get(f"{API}/branches", headers=h).json()
    services = requests.get(f"{API}/services", headers=h).json()
    stylists = requests.get(f"{API}/stylists", headers=h).json()
    assert branches and services, "Seed data missing"
    zona10 = next((b for b in branches if "10" in b["name"]), branches[0])
    return {"branch": zona10, "branches": branches, "services": services, "stylists": stylists}


class TestAgenda:
    def test_availability_slots(self, tokens, company_ctx):
        s = company_ctx["services"][0]
        b = company_ctx["branch"]
        r = requests.get(f"{API}/availability",
                         params={"branch_id": b["id"], "service_id": s["id"], "date": TEST_DATE},
                         headers=H(tokens, "admin"))
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data["slots"], list)
        assert len(data["slots"]) > 0, "Expected slots on Monday"

    def test_sunday_closed_for_zona10(self, tokens, company_ctx):
        zona10 = next((b for b in company_ctx["branches"] if "10" in b["name"]), None)
        if not zona10:
            pytest.skip("Zona 10 branch not found")
        s = company_ctx["services"][0]
        r = requests.get(f"{API}/availability",
                         params={"branch_id": zona10["id"], "service_id": s["id"], "date": TEST_DATE_SUNDAY},
                         headers=H(tokens, "admin"))
        assert r.status_code == 200
        data = r.json()
        assert data["slots"] == [], f"Expected Sunday closed, got {data['slots']}"

    def test_create_appointment_and_status(self, tokens, company_ctx):
        s = company_ctx["services"][0]
        b = company_ctx["branch"]
        avail = requests.get(f"{API}/availability",
                             params={"branch_id": b["id"], "service_id": s["id"], "date": TEST_DATE},
                             headers=H(tokens, "admin")).json()
        slot = avail["slots"][0]
        slot_time = slot["time"] if isinstance(slot, dict) else slot
        phone = f"+5025555{str(uuid.uuid4().int)[:4]}"
        r = requests.post(f"{API}/appointments", headers=H(tokens, "admin"), json={
            "branch_id": b["id"], "service_id": s["id"], "date": TEST_DATE, "time": slot_time,
            "phone": phone, "name": "TEST_Cliente"
        })
        assert r.status_code == 200, r.text
        appt = r.json()
        assert appt["status"] in ("pending", "confirmed")
        assert appt["date"] == TEST_DATE

        # Status change
        for status in ("confirmed", "completed"):
            r = requests.post(f"{API}/appointments/{appt['id']}/status",
                              headers=H(tokens, "admin"), json={"status": status})
            assert r.status_code == 200, r.text
            assert r.json()["status"] == status
        pytest.appt_id_for_cleanup = appt["id"]

    def test_booking_conflict_409(self, tokens, company_ctx):
        s = company_ctx["services"][0]
        b = company_ctx["branch"]
        avail = requests.get(f"{API}/availability",
                             params={"branch_id": b["id"], "service_id": s["id"], "date": TEST_DATE},
                             headers=H(tokens, "admin")).json()
        slot = avail["slots"][0]
        slot_time = slot["time"] if isinstance(slot, dict) else slot
        slot_stylist = slot.get("stylist_id") if isinstance(slot, dict) else None
        phone = f"+5025555{str(uuid.uuid4().int)[:4]}"
        # Book first
        r1 = requests.post(f"{API}/appointments", headers=H(tokens, "admin"), json={
            "branch_id": b["id"], "service_id": s["id"], "date": TEST_DATE, "time": slot_time,
            "phone": phone, "name": "TEST_Dup", "stylist_id": slot_stylist
        })
        if r1.status_code != 200:
            pytest.skip("Could not create initial appointment for conflict test")
        same_stylist = r1.json().get("stylist_id")
        r2 = requests.post(f"{API}/appointments", headers=H(tokens, "admin"), json={
            "branch_id": b["id"], "service_id": s["id"], "date": TEST_DATE, "time": slot_time,
            "phone": "+50255550099", "name": "TEST_Dup2", "stylist_id": same_stylist
        })
        # Either 409 (conflict) or 200 (auto-assigned different stylist)
        assert r2.status_code in (200, 409)


# ============== CRM ==============
class TestCRM:
    def test_list_clients(self, tokens):
        r = requests.get(f"{API}/clients", headers=H(tokens, "admin"))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_client_and_get(self, tokens):
        phone = f"+5025599{str(uuid.uuid4().int)[:4]}"
        r = requests.post(f"{API}/clients", headers=H(tokens, "admin"),
                          json={"phone": phone, "name": "TEST_Client", "email": "test_c@example.com"})
        assert r.status_code == 200, r.text
        cid = r.json()["id"]
        g = requests.get(f"{API}/clients/{cid}", headers=H(tokens, "admin"))
        assert g.status_code == 200
        d = g.json()
        assert "client" in d and "appointments" in d and "stats" in d
        assert d["client"]["phone"].endswith(phone[-6:])


# ============== Loyalty & Marketing ==============
class TestLoyaltyMarketing:
    def test_loyalty_get(self, tokens):
        r = requests.get(f"{API}/loyalty", headers=H(tokens, "admin"))
        assert r.status_code == 200
        assert "config" in r.json()

    def test_recommendations(self, tokens):
        r = requests.get(f"{API}/recommendations", headers=H(tokens, "admin"))
        assert r.status_code == 200

    def test_campaigns_list(self, tokens):
        r = requests.get(f"{API}/campaigns", headers=H(tokens, "admin"))
        assert r.status_code == 200


# ============== Reports ==============
class TestReports:
    @pytest.mark.parametrize("group", ["branch", "stylist", "service", "client"])
    def test_reports(self, tokens, group):
        r = requests.get(f"{API}/reports",
                         params={"start": "2026-09-01", "end": "2026-10-31", "group": group},
                         headers=H(tokens, "admin"))
        assert r.status_code == 200, r.text


# ============== Audit ==============
class TestAudit:
    def test_audit(self, tokens):
        r = requests.get(f"{API}/audit", headers=H(tokens, "admin"))
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ============== Role restrictions ==============
class TestRoleRestrictions:
    def test_stylist_sees_only_own(self, tokens):
        r = requests.get(f"{API}/appointments",
                         params={"start": TEST_DATE, "end": TEST_DATE},
                         headers=H(tokens, "stylist"))
        assert r.status_code == 200
        stylist_id = tokens["stylist"]["user"].get("stylist_id")
        for a in r.json():
            assert a.get("stylist_id") == stylist_id

    def test_receptionist_cannot_create_service(self, tokens):
        r = requests.post(f"{API}/services", headers=H(tokens, "reception"),
                          json={"name": "TEST_SRV", "duration": 30, "price": 50})
        assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"


# ============== Public portal ==============
class TestPublicPortal:
    def test_public_salon(self):
        r = requests.get(f"{API}/public/salon/{SLUG}")
        assert r.status_code == 200
        d = r.json()
        assert d["name"]
        assert d["branches"] and d["services"]

    def test_public_slots_and_book(self):
        salon = requests.get(f"{API}/public/salon/{SLUG}").json()
        b = next((x for x in salon["branches"] if "10" in x["name"]), salon["branches"][0])
        s = salon["services"][0]
        r = requests.get(f"{API}/public/salon/{SLUG}/slots",
                         params={"branch_id": b["id"], "service_id": s["id"], "date": TEST_DATE})
        assert r.status_code == 200
        slots = r.json()["slots"]
        assert slots, "No public slots"
        slot = slots[-1]
        slot_time = slot["time"] if isinstance(slot, dict) else slot
        phone = f"+5025599{str(uuid.uuid4().int)[:4]}"
        r2 = requests.post(f"{API}/public/salon/{SLUG}/book", json={
            "branch_id": b["id"], "service_id": s["id"], "date": TEST_DATE, "time": slot_time,
            "phone": phone, "name": "TEST_Portal"
        })
        assert r2.status_code == 200, r2.text
        aid = r2.json()["id"]
        # Lookup via phone
        my = requests.post(f"{API}/public/salon/{SLUG}/my", json={"phone": phone})
        assert my.status_code == 200
        assert any(a["id"] == aid for a in my.json())
        # Cancel
        cancel = requests.post(f"{API}/public/salon/{SLUG}/appointments/{aid}",
                               json={"phone": phone, "action": "cancel"})
        assert cancel.status_code == 200
        assert cancel.json()["status"] == "cancelled"


# ============== Waitlist via public ==============
class TestWaitlist:
    def test_public_waitlist(self):
        salon = requests.get(f"{API}/public/salon/{SLUG}").json()
        if not salon.get("waitlist"):
            pytest.skip("Waitlist module not enabled")
        b = salon["branches"][0]
        s = salon["services"][0]
        phone = f"+5025577{str(uuid.uuid4().int)[:4]}"
        r = requests.post(f"{API}/public/salon/{SLUG}/waitlist", json={
            "phone": phone, "name": "TEST_WL", "branch_id": b["id"],
            "service_id": s["id"], "date": TEST_DATE
        })
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "waiting"


# ============== WhatsApp inbound (simulated) ==============
class TestWhatsApp:
    def test_wa_inbound_requires_fields(self):
        r = requests.post(f"{API}/wa/inbound", json={"to": WA_NUMBER})
        assert r.status_code == 400

    def test_wa_inbound_unknown_number(self):
        r = requests.post(f"{API}/wa/inbound",
                          json={"to": "+50200000000", "from_phone": "+50255554444", "text": "Hola"})
        assert r.status_code == 404

    def test_wa_inbound_bot_reply(self):
        r = requests.post(f"{API}/wa/inbound",
                          json={"to": WA_NUMBER, "from_phone": "+50255557777", "text": "Hola"},
                          timeout=90)
        assert r.status_code == 200, r.text
        assert "reply" in r.json()
        assert r.json()["reply"]


# ============== Admin SaaS ==============
class TestAdmin:
    def test_admin_metrics(self, tokens):
        r = requests.get(f"{API}/admin/metrics", headers=H(tokens, "super"))
        assert r.status_code == 200
        d = r.json()
        assert "mrr" in d and "arr" in d

    def test_admin_companies(self, tokens):
        r = requests.get(f"{API}/admin/companies", headers=H(tokens, "super"))
        assert r.status_code == 200
        companies = r.json()
        assert any(c["slug"] == SLUG for c in companies)

    def test_admin_billing_run(self, tokens):
        r = requests.post(f"{API}/admin/billing/run", headers=H(tokens, "super"))
        assert r.status_code == 200

    def test_admin_export_excel(self, tokens):
        r = requests.get(f"{API}/admin/export", headers=H(tokens, "super"))
        assert r.status_code == 200
        assert "sheet" in r.headers.get("content-type", "").lower() or len(r.content) > 100

    def test_admin_non_super_forbidden(self, tokens):
        r = requests.get(f"{API}/admin/metrics", headers=H(tokens, "admin"))
        assert r.status_code == 403

    def test_admin_payments_list(self, tokens):
        r = requests.get(f"{API}/admin/payments", headers=H(tokens, "super"))
        assert r.status_code == 200


# ============== Signup ==============
class TestSignup:
    def test_duplicate_slug(self):
        r = requests.post(f"{API}/signup", json={
            "company_name": "Salón Bella Vida (Demo)",
            "slug": SLUG,
            "email": f"TEST_{uuid.uuid4().hex[:6]}@example.com",
            "password": "Pass2026!",
            "accept_terms": True,
            "plan_id": "",
        })
        # Expect 400/409 on duplicate slug OR 400 on invalid plan
        assert r.status_code in (400, 409), r.text

    def test_signup_success(self):
        plans = requests.get(f"{API}/public/plans").json()["plans"]
        plan = plans[0]
        slug = f"test-{uuid.uuid4().hex[:8]}"
        email = f"TEST_{uuid.uuid4().hex[:8]}@example.com"
        r = requests.post(f"{API}/signup", json={
            "company_name": f"TEST_Co_{slug}",
            "slug": slug,
            "email": email,
            "password": "Pass2026!",
            "contact_name": "Tester",
            "phone": "+50255550099",
            "whatsapp_number": "+50255550099",
            "accept_terms": True,
            "plan_id": plan["id"],
        })
        assert r.status_code == 200, r.text
        # Duplicate email
        r2 = requests.post(f"{API}/signup", json={
            "company_name": f"TEST_Co2_{uuid.uuid4().hex[:6]}",
            "slug": f"test-{uuid.uuid4().hex[:6]}",
            "email": email,
            "password": "Pass2026!",
            "accept_terms": True,
            "plan_id": plan["id"],
        })
        assert r2.status_code in (400, 409)


# ============== Suspension flow (restore at end) ==============
class TestSuspension:
    def test_suspended_portal_forbidden_and_restore(self, tokens):
        # Find bellavida company id
        companies = requests.get(f"{API}/admin/companies", headers=H(tokens, "super")).json()
        bv = next(c for c in companies if c["slug"] == SLUG)
        cid = bv["id"]
        try:
            # Suspend fully
            r = requests.put(f"{API}/admin/companies/{cid}", headers=H(tokens, "super"),
                             json={"status": "suspended"})
            assert r.status_code == 200
            # Public portal should 403
            p = requests.get(f"{API}/public/salon/{SLUG}")
            assert p.status_code == 403
            # WhatsApp should respond suspension msg
            w = requests.post(f"{API}/wa/inbound",
                              json={"to": WA_NUMBER, "from_phone": "+50255550020", "text": "Hola"},
                              timeout=30)
            assert w.status_code == 200
            # suspended_partial: writes should 402
            r2 = requests.put(f"{API}/admin/companies/{cid}", headers=H(tokens, "super"),
                              json={"status": "suspended_partial"})
            assert r2.status_code == 200
            # Create an appointment should be blocked
            salon_internal = requests.get(f"{API}/company", headers=H(tokens, "admin"))
            # Try create a service as admin - must be 402
            cr = requests.post(f"{API}/services", headers=H(tokens, "admin"),
                               json={"name": "TEST_SUSP", "duration": 30, "price": 10})
            assert cr.status_code in (402, 403), f"Expected 402/403, got {cr.status_code}: {cr.text}"
        finally:
            # Restore to active
            rr = requests.put(f"{API}/admin/companies/{cid}", headers=H(tokens, "super"),
                              json={"status": "active"})
            assert rr.status_code == 200
