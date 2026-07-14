"""Iteration 7 - Deployment fix regression tests.
Verifies:
  1. /api/dashboard/summary correctness after MongoDB projection changes.
  2. /api/workspaces/{id}/invite works when APP_URL env var is missing.
  3. /api/checks, /api/expenses, /api/incomes still return full records
     (projections applied ONLY to dashboard endpoint).
"""
import os
import time
import uuid
import pytest
import requests
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://cashflow-hub-444.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

mongo = MongoClient(MONGO_URL)
db = mongo[DB_NAME]


def _mk_user(prefix="dash"):
    ts = int(time.time() * 1000)
    uid = f"test-{prefix}-{ts}-{uuid.uuid4().hex[:4]}"
    tok = f"sess_{prefix}_{ts}_{uuid.uuid4().hex[:6]}"
    email = f"{prefix}.{ts}.{uuid.uuid4().hex[:4]}@testdash.com"
    db.users.insert_one({"user_id": uid, "email": email, "name": f"{prefix.title()} Test",
                         "picture": "", "created_at": datetime.now(timezone.utc)})
    db.user_sessions.insert_one({"user_id": uid, "session_token": tok,
                                 "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
                                 "created_at": datetime.now(timezone.utc)})
    return {"user_id": uid, "token": tok, "email": email, "name": f"{prefix.title()} Test"}


def _h(u):
    return {"Authorization": f"Bearer {u['token']}"}


@pytest.fixture(scope="module")
def seeded_user():
    u = _mk_user("regr")
    # Get workspace id
    me = requests.get(f"{API}/auth/me", headers=_h(u)).json()
    u["workspace_id"] = me["workspace_id"]

    # ---- Seed data via API ----
    # 2 bank accounts
    for bal in [1000.0, 500.5]:
        r = requests.post(f"{API}/bank-accounts", headers=_h(u), json={
            "name": f"TEST_A_{bal}", "bank_name": "TEST_BANK", "balance": bal
        })
        assert r.status_code == 200, r.text

    today = datetime.now(timezone.utc).date()
    within_30 = (today + timedelta(days=10)).isoformat()
    past = (today - timedelta(days=40)).isoformat()

    # Checks: received pending within 30d (200), issued pending within 30d (150), received cleared (should be excluded)
    for payload in [
        {"type": "received", "party": "TEST_C1", "amount": 200.0, "due_date": within_30, "status": "pending"},
        {"type": "issued",   "party": "TEST_C2", "amount": 150.0, "due_date": within_30, "status": "pending"},
        {"type": "received", "party": "TEST_C3", "amount": 999.0, "due_date": within_30, "status": "cleared"},
        {"type": "received", "party": "TEST_C4", "amount": 111.0, "due_date": past,      "status": "pending"},
    ]:
        r = requests.post(f"{API}/checks", headers=_h(u), json=payload)
        assert r.status_code == 200, r.text

    # Promissory notes: received pending within 30d (75)
    for payload in [
        {"type": "received", "party": "TEST_N1", "amount": 75.0, "due_date": within_30, "status": "pending"},
        {"type": "issued",   "party": "TEST_N2", "amount": 50.0, "due_date": within_30, "status": "pending"},
    ]:
        r = requests.post(f"{API}/promissory-notes", headers=_h(u), json=payload)
        assert r.status_code == 200, r.text

    # Expenses (current month, two categories)
    cm_date = today.replace(day=1).isoformat()
    for payload in [
        {"category": "TEST_Ofis", "description": "d1", "amount": 100.0, "date": cm_date, "vat_rate": 20.0},
        {"category": "TEST_Ofis", "description": "d2", "amount": 50.0,  "date": cm_date, "vat_rate": 20.0},
        {"category": "TEST_Yakit", "description": "d3", "amount": 30.0, "date": cm_date, "vat_rate": 20.0},
    ]:
        r = requests.post(f"{API}/expenses", headers=_h(u), json=payload)
        assert r.status_code == 200, r.text

    # Incomes (current month)
    for payload in [
        {"source": "TEST_S1", "description": "i1", "amount": 400.0, "date": cm_date, "vat_rate": 20.0},
        {"source": "TEST_S2", "description": "i2", "amount": 100.0, "date": cm_date, "vat_rate": 20.0},
    ]:
        r = requests.post(f"{API}/incomes", headers=_h(u), json=payload)
        assert r.status_code == 200, r.text

    yield u

    # Cleanup
    db.users.delete_one({"user_id": u["user_id"]})
    db.user_sessions.delete_many({"user_id": u["user_id"]})
    db.workspaces.delete_many({"owner_user_id": u["user_id"]})
    db.workspace_members.delete_many({"email": u["email"]})
    for coll in ["bank_accounts", "checks", "promissory_notes", "expenses", "incomes"]:
        db[coll].delete_many({"user_id": u["user_id"]})


# ============ Dashboard Summary Regression ============
class TestDashboardSummary:
    def test_summary_all_fields_present(self, seeded_user):
        r = requests.get(f"{API}/dashboard/summary", headers=_h(seeded_user))
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ["total_balance", "upcoming_incoming", "upcoming_outgoing",
                    "month_income", "month_expense", "monthly", "categories",
                    "upcoming", "accounts_count"]:
            assert key in d, f"Missing key {key}"

    def test_total_balance_correct(self, seeded_user):
        d = requests.get(f"{API}/dashboard/summary", headers=_h(seeded_user)).json()
        assert d["total_balance"] == round(1000.0 + 500.5, 2)
        assert d["accounts_count"] == 2

    def test_upcoming_amounts_correct(self, seeded_user):
        d = requests.get(f"{API}/dashboard/summary", headers=_h(seeded_user)).json()
        # received pending 200 (check) + 75 (note) = 275
        assert d["upcoming_incoming"] == 275.0
        # issued pending 150 (check) + 50 (note) = 200
        assert d["upcoming_outgoing"] == 200.0

    def test_month_totals_correct(self, seeded_user):
        d = requests.get(f"{API}/dashboard/summary", headers=_h(seeded_user)).json()
        assert d["month_income"] == 500.0  # 400 + 100
        assert d["month_expense"] == 180.0  # 100 + 50 + 30

    def test_categories_breakdown(self, seeded_user):
        d = requests.get(f"{API}/dashboard/summary", headers=_h(seeded_user)).json()
        cats = {c["name"]: c["value"] for c in d["categories"]}
        assert cats.get("TEST_Ofis") == 150.0
        assert cats.get("TEST_Yakit") == 30.0

    def test_monthly_array_shape(self, seeded_user):
        d = requests.get(f"{API}/dashboard/summary", headers=_h(seeded_user)).json()
        assert isinstance(d["monthly"], list)
        assert len(d["monthly"]) == 6
        for m in d["monthly"]:
            for k in ["month", "gelir", "gider", "net"]:
                assert k in m
        # last entry should be current month with income 500 and expense 180
        last = d["monthly"][-1]
        assert last["gelir"] == 500.0
        assert last["gider"] == 180.0
        assert last["net"] == 320.0

    def test_upcoming_list_contents(self, seeded_user):
        d = requests.get(f"{API}/dashboard/summary", headers=_h(seeded_user)).json()
        upcoming = d["upcoming"]
        # Should NOT contain the past-due check or the cleared check
        parties = [u["party"] for u in upcoming]
        assert "TEST_C1" in parties
        assert "TEST_C2" in parties
        assert "TEST_N1" in parties
        assert "TEST_N2" in parties
        assert "TEST_C3" not in parties  # cleared
        assert "TEST_C4" not in parties  # past date
        # Each entry has correct keys (from projection: id, type, status, amount, due_date, party)
        for item in upcoming:
            for k in ["id", "kind", "type", "party", "amount", "due_date"]:
                assert k in item, f"Missing {k} in upcoming item"


# ============ Invite Regression (APP_URL missing) ============
class TestInviteWithoutAppUrl:
    def test_invite_pending_without_app_url(self, seeded_user):
        # APP_URL is not set in backend/.env - verify no exception
        assert not os.environ.get("APP_URL"), "APP_URL should be unset for this test"
        new_email = f"TEST_invite.{uuid.uuid4().hex[:6]}@testdash.com"
        r = requests.post(
            f"{API}/workspaces/{seeded_user['workspace_id']}/invite",
            headers=_h(seeded_user),
            json={"email": new_email, "role": "viewer"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "pending"
        assert data["member_id"].startswith("mem_")
        # cleanup
        db.workspace_members.delete_one({"id": data["member_id"]})


# ============ Full-record CRUD list endpoints (no projection) ============
class TestListEndpointsNoProjection:
    def test_checks_returns_full_records(self, seeded_user):
        r = requests.get(f"{API}/checks", headers=_h(seeded_user))
        assert r.status_code == 200
        items = r.json()
        assert len(items) >= 4
        sample = items[0]
        # Fields that should still exist (NOT in dashboard projection)
        for f in ["id", "user_id", "type", "party", "amount", "due_date",
                  "bank_name", "check_number", "status", "notes", "created_at"]:
            assert f in sample, f"Missing field '{f}' in /api/checks response"

    def test_expenses_returns_full_records(self, seeded_user):
        r = requests.get(f"{API}/expenses", headers=_h(seeded_user))
        assert r.status_code == 200
        items = r.json()
        assert len(items) >= 3
        sample = items[0]
        for f in ["id", "user_id", "category", "description", "amount",
                  "vat_rate", "date", "created_at"]:
            assert f in sample, f"Missing field '{f}' in /api/expenses response"

    def test_incomes_returns_full_records(self, seeded_user):
        r = requests.get(f"{API}/incomes", headers=_h(seeded_user))
        assert r.status_code == 200
        items = r.json()
        assert len(items) >= 2
        sample = items[0]
        for f in ["id", "user_id", "source", "description", "amount",
                  "vat_rate", "date", "created_at"]:
            assert f in sample, f"Missing field '{f}' in /api/incomes response"
