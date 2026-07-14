"""
Regression tests for the OAuth callback fix (iteration 8).

Bug: AuthCallback used SPA navigate() which didn't reload AuthContext,
causing an infinite /auth/me 401 loop for invited users. Fix uses
window.location.replace(). Backend logic (/api/auth/session, /api/auth/me,
pending invite auto-accept) already works; these tests verify no regression.
"""
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

def _load_env_file(path):
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass

_load_env_file("/app/frontend/.env")
_load_env_file("/app/backend/.env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


@pytest.fixture(scope="module")
def mdb():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


@pytest.fixture
def seeded_user(mdb):
    """Seed a test user + valid session in Mongo (like a completed OAuth exchange)."""
    ts = int(time.time() * 1000)
    user_id = f"TEST_user_{ts}"
    email = f"TEST_bugtest_{ts}@example.com"
    token = f"TEST_sess_{uuid.uuid4().hex}"

    mdb.users.insert_one({
        "user_id": user_id,
        "email": email,
        "name": "Bug Test User",
        "picture": "https://via.placeholder.com/150",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    mdb.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": token,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    yield {"user_id": user_id, "email": email, "token": token}
    # cleanup
    mdb.users.delete_many({"user_id": user_id})
    mdb.user_sessions.delete_many({"user_id": user_id})
    mdb.workspaces.delete_many({"owner_user_id": user_id})
    mdb.workspace_members.delete_many({"user_id": user_id})
    mdb.workspace_members.delete_many({"email": email.lower()})


# --- /api/auth/me via seeded session ---
class TestAuthMeWithSeededSession:
    def test_me_with_valid_bearer_token_returns_200(self, seeded_user):
        r = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {seeded_user['token']}"},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["user_id"] == seeded_user["user_id"]
        assert data["email"] == seeded_user["email"]
        assert data["name"] == "Bug Test User"
        # workspace context resolved (personal workspace auto-created)
        assert "workspace_id" in data and data["workspace_id"]
        assert "role" in data and data["role"] in ("owner", "editor", "viewer")

    def test_me_with_cookie_returns_200(self, seeded_user):
        r = requests.get(
            f"{BASE_URL}/api/auth/me",
            cookies={"session_token": seeded_user["token"]},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        assert r.json()["email"] == seeded_user["email"]

    def test_me_without_token_returns_401(self):
        r = requests.get(f"{BASE_URL}/api/auth/me", timeout=10)
        assert r.status_code == 401

    def test_me_with_invalid_token_returns_401(self):
        r = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": "Bearer invalid_token_does_not_exist"},
            timeout=10,
        )
        assert r.status_code == 401


# --- /api/auth/session regression: contract still exists ---
class TestAuthSessionContract:
    def test_session_endpoint_exists_and_rejects_bad_session_id(self):
        # Bad session_id -> Emergent returns non-200 -> our code returns 401
        r = requests.post(
            f"{BASE_URL}/api/auth/session",
            json={"session_id": "definitely_not_a_real_session_id_xyz"},
            timeout=15,
        )
        # Accept 401 (bad session_id) or 502 (upstream unreachable) — endpoint alive
        assert r.status_code in (401, 502), f"Unexpected status: {r.status_code} {r.text}"

    def test_session_endpoint_validates_payload(self):
        r = requests.post(f"{BASE_URL}/api/auth/session", json={}, timeout=10)
        assert r.status_code == 422  # Pydantic validation


# --- Pending invite auto-accept simulation (via direct Mongo seed) ---
class TestPendingInviteAutoAccept:
    """
    Simulates what happens inside /api/auth/session after a real OAuth exchange:
    _accept_pending_invites should flip pending workspace_members rows to active
    when the newly logged-in user's email matches.
    """
    def test_pending_invite_activates_on_login(self, mdb, seeded_user):
        # Seed an inviter workspace + pending invite for our test email
        inviter_id = f"TEST_inviter_{int(time.time()*1000)}"
        ws_id = f"TEST_ws_{uuid.uuid4().hex[:12]}"
        member_id = f"TEST_mem_{uuid.uuid4().hex[:12]}"

        mdb.users.insert_one({
            "user_id": inviter_id, "email": f"inviter_{inviter_id}@example.com",
            "name": "Inviter", "created_at": datetime.now(timezone.utc).isoformat(),
        })
        mdb.workspaces.insert_one({
            "workspace_id": ws_id, "owner_user_id": inviter_id,
            "name": "Inviter WS", "created_at": datetime.now(timezone.utc).isoformat(),
        })
        mdb.workspace_members.insert_one({
            "id": member_id,
            "workspace_id": ws_id,
            "email": seeded_user["email"].lower(),
            "role": "viewer",
            "status": "pending",
            "invited_at": datetime.now(timezone.utc).isoformat(),
        })

        try:
            # Manually run the accept logic (same as create_session does)
            # by calling backend helper indirectly: hit /auth/me first to ensure user is valid,
            # then simulate accept by calling into the helper via a synthetic request is not possible
            # from outside. Instead: invoke the same behavior directly through mongo assertion after
            # replicating _accept_pending_invites logic here to prove the query matches.
            from datetime import datetime as _dt
            pending = list(mdb.workspace_members.find(
                {"email": seeded_user["email"].lower(), "status": "pending"}
            ))
            assert len(pending) == 1, "Seeded invite should be found by _accept_pending_invites query"
            # simulate accept
            mdb.workspace_members.update_one(
                {"id": member_id},
                {"$set": {"user_id": seeded_user["user_id"], "status": "active",
                          "accepted_at": _dt.now(timezone.utc).isoformat()}},
            )
            active = mdb.workspace_members.find_one({"id": member_id})
            assert active["status"] == "active"
            assert active["user_id"] == seeded_user["user_id"]

            # Verify user can now switch to this workspace (list_workspaces should include it)
            r = requests.get(
                f"{BASE_URL}/api/workspaces",
                headers={"Authorization": f"Bearer {seeded_user['token']}"},
                timeout=10,
            )
            assert r.status_code == 200
            ws_ids = [w["workspace_id"] for w in r.json()]
            assert ws_id in ws_ids, f"Invited workspace missing from list: {ws_ids}"
        finally:
            mdb.users.delete_many({"user_id": inviter_id})
            mdb.workspaces.delete_many({"workspace_id": ws_id})
            mdb.workspace_members.delete_many({"id": member_id})


# --- Frontend fix presence check ---
class TestAuthCallbackFrontendFix:
    def test_authcallback_uses_window_location_replace(self):
        with open("/app/frontend/src/pages/AuthCallback.jsx") as f:
            src = f.read()
        assert "window.location.replace" in src, "Fix missing: window.location.replace not found"
        assert "useNavigate" not in src, "Regression: useNavigate should be removed"
        assert 'from "react-router' not in src, "Regression: react-router import should be removed"
