"""
Iteration 10 - Role-based authorization enforcement tests.

Verifies that write endpoints reject `viewer` role with HTTP 403 and the
Turkish message "Bu workspace'de salt okur yetkiniz var", while allowing
read endpoints and editor/owner writes.

Seeds test users (owner, editor, viewer) + one shared workspace + sessions
directly in Mongo.
"""
import os
import sys
import uuid
import asyncio
import pytest
import requests
from datetime import datetime, timedelta, timezone
from motor.motor_asyncio import AsyncIOMotorClient

# Load backend .env
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else "https://cashflow-hub-444.preview.emergentagent.com"
API = f"{BASE_URL}/api"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

EXPECTED_403_MSG = "Bu workspace'de salt okur yetkiniz var"

TEST_PREFIX = "TEST_ROLES_"
OWNER_ID = f"{TEST_PREFIX}owner"
EDITOR_ID = f"{TEST_PREFIX}editor"
VIEWER_ID = f"{TEST_PREFIX}viewer"
WORKSPACE_ID = f"{TEST_PREFIX}ws_1"

OWNER_TOKEN = f"{TEST_PREFIX}tok_owner"
EDITOR_TOKEN = f"{TEST_PREFIX}tok_editor"
VIEWER_TOKEN = f"{TEST_PREFIX}tok_viewer"


@pytest.fixture(scope="session", autouse=True)
def seed_and_cleanup():
    """Seed users, workspace, members, sessions, and clean up after."""
    async def _setup():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]

        now = datetime.now(timezone.utc)
        expires = (now + timedelta(days=1)).isoformat()

        # Clean any prior
        for coll in ["users", "user_sessions", "workspaces", "workspace_members",
                     "bank_accounts", "checks", "promissory_notes", "expenses",
                     "incomes", "backups"]:
            await db[coll].delete_many({"user_id": {"$in": [OWNER_ID, EDITOR_ID, VIEWER_ID]}})
            await db[coll].delete_many({"workspace_id": WORKSPACE_ID})
        await db.users.delete_many({"user_id": {"$in": [OWNER_ID, EDITOR_ID, VIEWER_ID]}})
        await db.user_sessions.delete_many({"session_token": {"$in": [OWNER_TOKEN, EDITOR_TOKEN, VIEWER_TOKEN]}})

        # Users
        for uid, email, name in [
            (OWNER_ID, "test_roles_owner@example.com", "Owner Test"),
            (EDITOR_ID, "test_roles_editor@example.com", "Editor Test"),
            (VIEWER_ID, "test_roles_viewer@example.com", "Viewer Test"),
        ]:
            await db.users.insert_one({
                "user_id": uid, "email": email, "name": name,
                "picture": "", "active_workspace_id": WORKSPACE_ID,
                "created_at": now.isoformat(),
            })

        # Workspace owned by owner
        await db.workspaces.insert_one({
            "workspace_id": WORKSPACE_ID,
            "owner_user_id": OWNER_ID,
            "name": "TEST_ROLES Shared WS",
            "created_at": now.isoformat(),
        })

        # Members
        await db.workspace_members.insert_many([
            {
                "id": str(uuid.uuid4()), "workspace_id": WORKSPACE_ID,
                "user_id": EDITOR_ID, "email": "test_roles_editor@example.com",
                "name": "Editor Test", "role": "editor", "status": "active",
                "invited_at": now.isoformat(), "accepted_at": now.isoformat(),
            },
            {
                "id": str(uuid.uuid4()), "workspace_id": WORKSPACE_ID,
                "user_id": VIEWER_ID, "email": "test_roles_viewer@example.com",
                "name": "Viewer Test", "role": "viewer", "status": "active",
                "invited_at": now.isoformat(), "accepted_at": now.isoformat(),
            },
        ])

        # Sessions
        for uid, tok in [(OWNER_ID, OWNER_TOKEN), (EDITOR_ID, EDITOR_TOKEN), (VIEWER_ID, VIEWER_TOKEN)]:
            await db.user_sessions.insert_one({
                "session_token": tok, "user_id": uid, "expires_at": expires,
                "created_at": now.isoformat(),
            })

        client.close()

    async def _teardown():
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        for coll in ["users", "user_sessions", "workspaces", "workspace_members",
                     "bank_accounts", "checks", "promissory_notes", "expenses",
                     "incomes", "backups"]:
            await db[coll].delete_many({"user_id": {"$in": [OWNER_ID, EDITOR_ID, VIEWER_ID]}})
            await db[coll].delete_many({"workspace_id": WORKSPACE_ID})
        await db.users.delete_many({"user_id": {"$in": [OWNER_ID, EDITOR_ID, VIEWER_ID]}})
        await db.user_sessions.delete_many({"session_token": {"$in": [OWNER_TOKEN, EDITOR_TOKEN, VIEWER_TOKEN]}})
        client.close()

    asyncio.get_event_loop().run_until_complete(_setup())
    yield
    asyncio.get_event_loop().run_until_complete(_teardown())


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ---------------- Setup: owner creates one of each resource ---------------
@pytest.fixture(scope="session")
def owner_created_ids(seed_and_cleanup):
    """Owner creates one of each resource; returns dict of ids."""
    ids = {}
    # bank account
    r = requests.post(f"{API}/bank-accounts", headers=_hdr(OWNER_TOKEN), json={
        "name": "TEST_ROLES Acc", "bank_name": "TEST_ROLES Bank",
        "account_number": "000001", "balance": 1000, "currency": "TRY"
    })
    assert r.status_code == 200, r.text
    ids["bank_account"] = r.json()["id"]

    # check
    r = requests.post(f"{API}/checks", headers=_hdr(OWNER_TOKEN), json={
        "type": "received", "party": "TEST_ROLES party", "amount": 500,
        "due_date": "2026-02-01", "bank_name": "B", "check_number": "CHK-1",
        "status": "pending"
    })
    assert r.status_code == 200, r.text
    ids["check"] = r.json()["id"]

    # promissory-note
    r = requests.post(f"{API}/promissory-notes", headers=_hdr(OWNER_TOKEN), json={
        "type": "received", "party": "TEST_ROLES party", "amount": 300,
        "due_date": "2026-02-01", "status": "pending"
    })
    assert r.status_code == 200, r.text
    ids["note"] = r.json()["id"]

    # expense
    r = requests.post(f"{API}/expenses", headers=_hdr(OWNER_TOKEN), json={
        "category": "other", "description": "TEST_ROLES exp",
        "amount": 100, "date": "2026-01-01"
    })
    assert r.status_code == 200, r.text
    ids["expense"] = r.json()["id"]

    # income
    r = requests.post(f"{API}/incomes", headers=_hdr(OWNER_TOKEN), json={
        "source": "TEST_ROLES src", "description": "TEST_ROLES inc",
        "amount": 200, "date": "2026-01-01"
    })
    assert r.status_code == 200, r.text
    ids["income"] = r.json()["id"]

    # backup (no body needed)
    r = requests.post(f"{API}/backups", headers=_hdr(OWNER_TOKEN))
    assert r.status_code == 200, r.text
    ids["backup"] = r.json()["id"]
    return ids


# ---------------- VIEWER: writes must return 403 with turkish message -------
class TestViewerWriteBlocked:
    def _assert_403(self, r):
        assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"
        j = r.json()
        assert j.get("detail") == EXPECTED_403_MSG, f"Bad msg: {j}"

    def test_viewer_create_bank_account(self, owner_created_ids):
        r = requests.post(f"{API}/bank-accounts", headers=_hdr(VIEWER_TOKEN), json={
            "name": "X", "bank_name": "Y", "balance": 0
        })
        self._assert_403(r)

    def test_viewer_update_bank_account(self, owner_created_ids):
        r = requests.put(f"{API}/bank-accounts/{owner_created_ids['bank_account']}",
                         headers=_hdr(VIEWER_TOKEN), json={
                             "name": "X", "bank_name": "Y", "balance": 0
                         })
        self._assert_403(r)

    def test_viewer_delete_bank_account(self, owner_created_ids):
        r = requests.delete(f"{API}/bank-accounts/{owner_created_ids['bank_account']}",
                            headers=_hdr(VIEWER_TOKEN))
        self._assert_403(r)

    def test_viewer_create_check(self, owner_created_ids):
        r = requests.post(f"{API}/checks", headers=_hdr(VIEWER_TOKEN), json={
            "type": "received", "party": "X", "amount": 1, "due_date": "2026-02-01"
        })
        self._assert_403(r)

    def test_viewer_update_check(self, owner_created_ids):
        r = requests.put(f"{API}/checks/{owner_created_ids['check']}",
                         headers=_hdr(VIEWER_TOKEN), json={
                             "type": "received", "party": "X", "amount": 1, "due_date": "2026-02-01"
                         })
        self._assert_403(r)

    def test_viewer_delete_check(self, owner_created_ids):
        r = requests.delete(f"{API}/checks/{owner_created_ids['check']}",
                            headers=_hdr(VIEWER_TOKEN))
        self._assert_403(r)

    def test_viewer_create_note(self, owner_created_ids):
        r = requests.post(f"{API}/promissory-notes", headers=_hdr(VIEWER_TOKEN), json={
            "type": "received", "party": "X", "amount": 1, "due_date": "2026-02-01"
        })
        self._assert_403(r)

    def test_viewer_update_note(self, owner_created_ids):
        r = requests.put(f"{API}/promissory-notes/{owner_created_ids['note']}",
                         headers=_hdr(VIEWER_TOKEN), json={
                             "type": "received", "party": "X", "amount": 1, "due_date": "2026-02-01"
                         })
        self._assert_403(r)

    def test_viewer_delete_note(self, owner_created_ids):
        r = requests.delete(f"{API}/promissory-notes/{owner_created_ids['note']}",
                            headers=_hdr(VIEWER_TOKEN))
        self._assert_403(r)

    def test_viewer_create_expense(self, owner_created_ids):
        r = requests.post(f"{API}/expenses", headers=_hdr(VIEWER_TOKEN), json={
            "category": "other", "description": "X", "amount": 1, "date": "2026-01-01"
        })
        self._assert_403(r)

    def test_viewer_update_expense(self, owner_created_ids):
        r = requests.put(f"{API}/expenses/{owner_created_ids['expense']}",
                         headers=_hdr(VIEWER_TOKEN), json={
                             "category": "other", "description": "X", "amount": 1, "date": "2026-01-01"
                         })
        self._assert_403(r)

    def test_viewer_delete_expense(self, owner_created_ids):
        r = requests.delete(f"{API}/expenses/{owner_created_ids['expense']}",
                            headers=_hdr(VIEWER_TOKEN))
        self._assert_403(r)

    def test_viewer_create_income(self, owner_created_ids):
        """CRITICAL: check that POST /incomes enforces require_write."""
        r = requests.post(f"{API}/incomes", headers=_hdr(VIEWER_TOKEN), json={
            "source": "X", "description": "X", "amount": 1, "date": "2026-01-01"
        })
        self._assert_403(r)

    def test_viewer_update_income(self, owner_created_ids):
        r = requests.put(f"{API}/incomes/{owner_created_ids['income']}",
                         headers=_hdr(VIEWER_TOKEN), json={
                             "source": "X", "description": "X", "amount": 1, "date": "2026-01-01"
                         })
        self._assert_403(r)

    def test_viewer_delete_income(self, owner_created_ids):
        r = requests.delete(f"{API}/incomes/{owner_created_ids['income']}",
                            headers=_hdr(VIEWER_TOKEN))
        self._assert_403(r)

    def test_viewer_create_backup(self, owner_created_ids):
        r = requests.post(f"{API}/backups", headers=_hdr(VIEWER_TOKEN))
        self._assert_403(r)

    def test_viewer_delete_backup(self, owner_created_ids):
        r = requests.delete(f"{API}/backups/{owner_created_ids['backup']}",
                            headers=_hdr(VIEWER_TOKEN))
        self._assert_403(r)

    def test_viewer_restore_backup(self, owner_created_ids):
        r = requests.post(f"{API}/backups/{owner_created_ids['backup']}/restore",
                          headers=_hdr(VIEWER_TOKEN))
        self._assert_403(r)

    def test_viewer_restore_file(self, owner_created_ids):
        h = {"Authorization": f"Bearer {VIEWER_TOKEN}"}
        files = {"file": ("b.json", b'{"version":1,"payload":{}}', "application/json")}
        r = requests.post(f"{API}/backups/restore-file", headers=h, files=files)
        self._assert_403(r)

    def test_viewer_import(self, owner_created_ids):
        h = {"Authorization": f"Bearer {VIEWER_TOKEN}"}
        files = {"file": ("x.csv", b"a,b\n1,2\n", "text/csv")}
        r = requests.post(f"{API}/import/expenses", headers=h, files=files)
        self._assert_403(r)


# ---------------- VIEWER: reads must succeed --------------------------------
class TestViewerReadsAllowed:
    @pytest.mark.parametrize("path", [
        "/bank-accounts", "/checks", "/promissory-notes",
        "/expenses", "/incomes", "/dashboard/summary", "/notifications"
    ])
    def test_viewer_get(self, owner_created_ids, path):
        r = requests.get(f"{API}{path}", headers=_hdr(VIEWER_TOKEN))
        assert r.status_code == 200, f"GET {path} -> {r.status_code}: {r.text}"


# ---------------- EDITOR: writes must succeed -------------------------------
class TestEditorWritesAllowed:
    def test_editor_create_expense(self, owner_created_ids):
        r = requests.post(f"{API}/expenses", headers=_hdr(EDITOR_TOKEN), json={
            "category": "other", "description": "TEST_ROLES editor exp",
            "amount": 50, "date": "2026-01-01"
        })
        assert r.status_code == 200, r.text
        assert r.json()["description"] == "TEST_ROLES editor exp"

    def test_editor_create_income(self, owner_created_ids):
        r = requests.post(f"{API}/incomes", headers=_hdr(EDITOR_TOKEN), json={
            "source": "TEST_ROLES editor", "description": "TEST_ROLES editor inc",
            "amount": 60, "date": "2026-01-01"
        })
        assert r.status_code == 200, r.text

    def test_editor_update_bank_account(self, owner_created_ids):
        r = requests.put(f"{API}/bank-accounts/{owner_created_ids['bank_account']}",
                         headers=_hdr(EDITOR_TOKEN), json={
                             "name": "TEST_ROLES Acc Edited", "bank_name": "TEST_ROLES Bank",
                             "balance": 1500
                         })
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "TEST_ROLES Acc Edited"


# ---------------- OWNER regression: writes still succeed --------------------
class TestOwnerWritesAllowed:
    def test_owner_update_income(self, owner_created_ids):
        r = requests.put(f"{API}/incomes/{owner_created_ids['income']}",
                         headers=_hdr(OWNER_TOKEN), json={
                             "source": "TEST_ROLES", "description": "TEST_ROLES inc edited",
                             "amount": 250, "date": "2026-01-01"
                         })
        assert r.status_code == 200, r.text

    def test_owner_delete_expense(self, owner_created_ids):
        # separate create then delete
        c = requests.post(f"{API}/expenses", headers=_hdr(OWNER_TOKEN), json={
            "category": "other", "description": "TEST_ROLES owner del",
            "amount": 5, "date": "2026-01-01"
        })
        eid = c.json()["id"]
        r = requests.delete(f"{API}/expenses/{eid}", headers=_hdr(OWNER_TOKEN))
        assert r.status_code == 200, r.text


# ---------------- Workspace management regression ---------------------------
class TestWorkspaceMgmtOwnerOnly:
    def test_editor_cannot_invite(self, owner_created_ids):
        r = requests.post(f"{API}/workspaces/{WORKSPACE_ID}/invite",
                          headers=_hdr(EDITOR_TOKEN),
                          json={"email": "someone@example.com", "role": "viewer"})
        assert r.status_code in (403, 401), f"Editor invite -> {r.status_code}: {r.text}"

    def test_viewer_cannot_invite(self, owner_created_ids):
        r = requests.post(f"{API}/workspaces/{WORKSPACE_ID}/invite",
                          headers=_hdr(VIEWER_TOKEN),
                          json={"email": "someone@example.com", "role": "viewer"})
        assert r.status_code in (403, 401), r.text

    def test_editor_cannot_rename(self, owner_created_ids):
        r = requests.put(f"{API}/workspaces/{WORKSPACE_ID}/rename",
                         headers=_hdr(EDITOR_TOKEN), json={"name": "x"})
        assert r.status_code in (403, 401), r.text
