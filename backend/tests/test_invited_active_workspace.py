"""
Tests for invited-user active_workspace_id behavior.

Bug: When a user was invited to a shared workspace and logged in for the first
time, their active_workspace_id remained None, so /auth/me returned their
personal (empty) workspace as owner instead of the invited shared workspace.

Fix: _accept_pending_invites now sets active_workspace_id to the first pending
invite's workspace when the user has none.
"""
import os
import sys
import uuid
import asyncio
import pytest
import requests
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")

# Load backend db + function
sys.path.insert(0, "/app/backend")
from server import _accept_pending_invites, _ensure_personal_workspace, db  # noqa: E402


def _rand(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# --------------- Helpers ---------------

async def _seed_owner_with_workspace(email, name):
    uid = _rand("user")
    await db.users.insert_one({
        "user_id": uid, "email": email, "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    ws_id = await _ensure_personal_workspace(uid, f"{name} - Kişisel")
    return uid, ws_id


async def _seed_pending_invite(workspace_id, email, role="viewer"):
    mid = _rand("mem")
    await db.workspace_members.insert_one({
        "id": mid,
        "workspace_id": workspace_id,
        "user_id": None,
        "email": email.lower(),
        "name": None,
        "role": role,
        "status": "pending",
        "invited_at": datetime.now(timezone.utc).isoformat(),
    })
    return mid


async def _seed_user_no_active(email, name):
    uid = _rand("user")
    await db.users.insert_one({
        "user_id": uid, "email": email, "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return uid


async def _seed_session(user_id):
    token = _rand("tok") + uuid.uuid4().hex
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": token,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return token


async def _cleanup(user_ids=None, ws_ids=None, emails=None):
    if user_ids:
        await db.users.delete_many({"user_id": {"$in": user_ids}})
        await db.user_sessions.delete_many({"user_id": {"$in": user_ids}})
        await db.workspace_members.delete_many({"user_id": {"$in": user_ids}})
    if ws_ids:
        await db.workspaces.delete_many({"workspace_id": {"$in": ws_ids}})
        await db.workspace_members.delete_many({"workspace_id": {"$in": ws_ids}})
    if emails:
        await db.workspace_members.delete_many({"email": {"$in": [e.lower() for e in emails]}})


# --------------- Tests ---------------

class TestAcceptPendingInvitesSetsActive:
    """Verify _accept_pending_invites sets active_workspace_id when missing."""

    def test_invited_user_lands_in_shared_workspace(self):
        owner_email = f"TEST_owner_{uuid.uuid4().hex[:6]}@ex.com"
        invitee_email = f"TEST_invitee_{uuid.uuid4().hex[:6]}@ex.com"

        async def run():
            owner_uid, ws_id = await _seed_owner_with_workspace(owner_email, "Owner")
            await _seed_pending_invite(ws_id, invitee_email, role="viewer")

            invitee_uid = await _seed_user_no_active(invitee_email, "Invitee")
            # Confirm no active_workspace_id yet
            u = await db.users.find_one({"user_id": invitee_uid}, {"_id": 0})
            assert u.get("active_workspace_id") is None

            # Simulate what create_session does after ensuring personal ws
            await _ensure_personal_workspace(invitee_uid, "Invitee - Kişisel")
            await _accept_pending_invites(invitee_uid, invitee_email, "Invitee")

            u2 = await db.users.find_one({"user_id": invitee_uid}, {"_id": 0})
            assert u2.get("active_workspace_id") == ws_id, (
                f"Expected active_workspace_id to be shared ws {ws_id}, got {u2.get('active_workspace_id')}"
            )

            # Invite record should now be active
            m = await db.workspace_members.find_one({"workspace_id": ws_id, "user_id": invitee_uid}, {"_id": 0})
            assert m["status"] == "active"
            assert m["role"] == "viewer"

            # Cleanup
            personal = await db.workspaces.find_one({"owner_user_id": invitee_uid}, {"_id": 0})
            await _cleanup(
                user_ids=[owner_uid, invitee_uid],
                ws_ids=[ws_id] + ([personal["workspace_id"]] if personal else []),
                emails=[invitee_email],
            )

        _run(run())

    def test_user_without_invites_keeps_personal_active(self):
        email = f"TEST_solo_{uuid.uuid4().hex[:6]}@ex.com"

        async def run():
            uid = await _seed_user_no_active(email, "Solo")
            ws_id = await _ensure_personal_workspace(uid, "Solo - Kişisel")
            await _accept_pending_invites(uid, email, "Solo")

            u = await db.users.find_one({"user_id": uid}, {"_id": 0})
            # Should remain None (no invites accepted, so no auto-set)
            assert u.get("active_workspace_id") is None, (
                f"User without invites should not have active_workspace_id set; got {u.get('active_workspace_id')}"
            )

            await _cleanup(user_ids=[uid], ws_ids=[ws_id], emails=[email])

        _run(run())

    def test_existing_active_workspace_not_overwritten(self):
        """User who already has active_workspace_id (e.g. their personal) should not be overwritten."""
        owner_email = f"TEST_owner2_{uuid.uuid4().hex[:6]}@ex.com"
        invitee_email = f"TEST_inv2_{uuid.uuid4().hex[:6]}@ex.com"

        async def run():
            owner_uid, ws_id = await _seed_owner_with_workspace(owner_email, "Owner2")
            await _seed_pending_invite(ws_id, invitee_email, role="editor")

            invitee_uid = await _seed_user_no_active(invitee_email, "Inv2")
            personal_ws = await _ensure_personal_workspace(invitee_uid, "Inv2 - Kişisel")
            # Manually set active to personal first (simulating existing user)
            await db.users.update_one({"user_id": invitee_uid}, {"$set": {"active_workspace_id": personal_ws}})

            await _accept_pending_invites(invitee_uid, invitee_email, "Inv2")

            u = await db.users.find_one({"user_id": invitee_uid}, {"_id": 0})
            assert u.get("active_workspace_id") == personal_ws, (
                "Existing active_workspace_id should not be overwritten by invite acceptance"
            )

            await _cleanup(
                user_ids=[owner_uid, invitee_uid],
                ws_ids=[ws_id, personal_ws],
                emails=[invitee_email],
            )

        _run(run())


class TestAuthMeEndpoint:
    """Verify /api/auth/me returns the shared workspace with viewer role for invited user."""

    def test_auth_me_returns_shared_workspace_for_invited_user(self):
        owner_email = f"TEST_owner3_{uuid.uuid4().hex[:6]}@ex.com"
        invitee_email = f"TEST_inv3_{uuid.uuid4().hex[:6]}@ex.com"

        async def setup():
            owner_uid, ws_id = await _seed_owner_with_workspace(owner_email, "Owner3")
            await _seed_pending_invite(ws_id, invitee_email, role="viewer")
            invitee_uid = await _seed_user_no_active(invitee_email, "Inv3")
            await _ensure_personal_workspace(invitee_uid, "Inv3 - Kişisel")
            await _accept_pending_invites(invitee_uid, invitee_email, "Inv3")
            token = await _seed_session(invitee_uid)
            return owner_uid, invitee_uid, ws_id, token

        owner_uid, invitee_uid, ws_id, token = _run(setup())

        r = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {token}"}, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["workspace_id"] == ws_id, f"Expected shared ws {ws_id}, got {data.get('workspace_id')}"
        assert data["role"] == "viewer", f"Expected role viewer, got {data.get('role')}"
        assert data["email"] == invitee_email

        # Also list workspaces
        r2 = requests.get(f"{BASE_URL}/api/workspaces", headers={"Authorization": f"Bearer {token}"}, timeout=15)
        assert r2.status_code == 200, r2.text
        ws_list = r2.json()
        # Should include both personal (owner) and shared (viewer)
        roles = {w["workspace_id"]: w for w in ws_list}
        assert ws_id in roles, f"Shared ws missing from list: {ws_list}"
        assert roles[ws_id]["role"] == "viewer"
        assert roles[ws_id]["is_active"] is True
        # Personal ws should also be present
        personal_entries = [w for w in ws_list if w["role"] == "owner"]
        assert len(personal_entries) >= 1

        async def teardown():
            personal = await db.workspaces.find_one({"owner_user_id": invitee_uid}, {"_id": 0})
            await _cleanup(
                user_ids=[owner_uid, invitee_uid],
                ws_ids=[ws_id] + ([personal["workspace_id"]] if personal else []),
                emails=[invitee_email],
            )
        _run(teardown())

    def test_workspace_switch_between_personal_and_shared(self):
        owner_email = f"TEST_owner4_{uuid.uuid4().hex[:6]}@ex.com"
        invitee_email = f"TEST_inv4_{uuid.uuid4().hex[:6]}@ex.com"

        async def setup():
            owner_uid, ws_id = await _seed_owner_with_workspace(owner_email, "Owner4")
            await _seed_pending_invite(ws_id, invitee_email, role="editor")
            invitee_uid = await _seed_user_no_active(invitee_email, "Inv4")
            personal_ws = await _ensure_personal_workspace(invitee_uid, "Inv4 - Kişisel")
            await _accept_pending_invites(invitee_uid, invitee_email, "Inv4")
            token = await _seed_session(invitee_uid)
            return owner_uid, invitee_uid, ws_id, personal_ws, token

        owner_uid, invitee_uid, ws_id, personal_ws, token = _run(setup())
        headers = {"Authorization": f"Bearer {token}"}

        # currently on shared
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=headers, timeout=15).json()
        assert me["workspace_id"] == ws_id

        # switch to personal
        r = requests.post(f"{BASE_URL}/api/workspaces/switch", headers=headers,
                          json={"workspace_id": personal_ws}, timeout=15)
        assert r.status_code == 200, r.text
        me2 = requests.get(f"{BASE_URL}/api/auth/me", headers=headers, timeout=15).json()
        assert me2["workspace_id"] == personal_ws
        assert me2["role"] == "owner"

        # switch back to shared
        r = requests.post(f"{BASE_URL}/api/workspaces/switch", headers=headers,
                          json={"workspace_id": ws_id}, timeout=15)
        assert r.status_code == 200
        me3 = requests.get(f"{BASE_URL}/api/auth/me", headers=headers, timeout=15).json()
        assert me3["workspace_id"] == ws_id
        assert me3["role"] == "editor"

        async def teardown():
            await _cleanup(
                user_ids=[owner_uid, invitee_uid],
                ws_ids=[ws_id, personal_ws],
                emails=[invitee_email],
            )
        _run(teardown())


class TestExistingAffectedUser:
    """Hotfix data verification for artemarble34@gmail.com."""

    def test_artemarble_active_workspace_is_shared(self):
        async def run():
            u = await db.users.find_one({"email": "artemarble34@gmail.com"}, {"_id": 0})
            assert u is not None, "User artemarble34 not found"
            assert u.get("active_workspace_id") == "ws_189740c5b90a", (
                f"Expected active_workspace_id=ws_189740c5b90a, got {u.get('active_workspace_id')}"
            )
            m = await db.workspace_members.find_one(
                {"workspace_id": "ws_189740c5b90a", "user_id": u["user_id"], "status": "active"}, {"_id": 0}
            )
            assert m is not None
            assert m["role"] == "viewer"
        _run(run())
