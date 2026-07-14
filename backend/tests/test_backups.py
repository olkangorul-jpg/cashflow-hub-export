"""Iteration 7: Backup/Restore endpoint tests."""
import os
import io
import json
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
TOKEN = os.environ.get("TEST_SESSION_TOKEN")


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {TOKEN}"})
    return s


@pytest.fixture(scope="module")
def seed(client):
    """Create one of each: bank_account, check, promissory_note, expense, income."""
    created = []
    # bank_account
    r = client.post(f"{BASE_URL}/api/bank-accounts", json={
        "name": "TEST_BAK_account", "bank_name": "TEST_BAK_bank", "currency": "TRY", "balance": 1000
    })
    assert r.status_code in (200, 201), r.text
    created.append(("bank-accounts", r.json()["id"]))

    # income
    r = client.post(f"{BASE_URL}/api/incomes", json={
        "source": "TEST_BAK_inc", "description": "test", "amount": 500, "date": "2026-07-01"
    })
    assert r.status_code in (200, 201), r.text
    created.append(("incomes", r.json()["id"]))

    # expense
    r = client.post(f"{BASE_URL}/api/expenses", json={
        "category": "TEST_BAK_exp", "description": "test", "amount": 100, "date": "2026-07-02"
    })
    assert r.status_code in (200, 201), r.text
    created.append(("expenses", r.json()["id"]))

    # check
    r = client.post(f"{BASE_URL}/api/checks", json={
        "type": "issued", "party": "TEST_BAK_cp", "amount": 200,
        "due_date": "2026-08-01", "status": "pending"
    })
    assert r.status_code in (200, 201), r.text
    created.append(("checks", r.json()["id"]))

    # promissory note
    r = client.post(f"{BASE_URL}/api/promissory-notes", json={
        "type": "issued", "party": "TEST_BAK_cp2", "amount": 300,
        "due_date": "2026-09-01", "status": "pending"
    })
    assert r.status_code in (200, 201), r.text
    created.append(("promissory-notes", r.json()["id"]))

    yield created
    # Cleanup any surviving records
    for coll, _id in created:
        try:
            client.delete(f"{BASE_URL}/api/{coll}/{_id}")
        except Exception:
            pass


class TestBackupCRUD:
    def test_create_backup(self, client, seed):
        r = client.post(f"{BASE_URL}/api/backups")
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["kind"] == "manual"
        assert b["total_records"] >= 5
        assert b["size_bytes"] > 0
        assert b["id"].startswith("bak_")
        pytest.backup_id = b["id"]

    def test_list_backups_metadata_only(self, client):
        r = client.get(f"{BASE_URL}/api/backups")
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list) and len(items) >= 1
        # Payload must be excluded from list response
        assert "payload" not in items[0]
        assert items[0]["kind"] in ("manual", "auto")
        # Sorted desc
        ts = [x["created_at"] for x in items]
        assert ts == sorted(ts, reverse=True)

    def test_download_backup(self, client):
        bid = pytest.backup_id
        r = client.get(f"{BASE_URL}/api/backups/{bid}/download")
        assert r.status_code == 200
        assert "application/json" in r.headers.get("content-type", "")
        assert "attachment" in r.headers.get("content-disposition", "")
        data = r.json()
        assert data["version"] == 1
        assert "payload" in data
        for c in ["bank_accounts", "checks", "promissory_notes", "expenses", "incomes"]:
            assert c in data["payload"]

    def test_restore_merge_doubles_records(self, client):
        bid = pytest.backup_id
        # Count existing expenses
        r0 = client.get(f"{BASE_URL}/api/expenses")
        before = len(r0.json())
        r = client.post(f"{BASE_URL}/api/backups/{bid}/restore?mode=merge")
        assert r.status_code == 200, r.text
        assert r.json()["mode"] == "merge"
        assert r.json()["restored"] >= 5
        r1 = client.get(f"{BASE_URL}/api/expenses")
        after = len(r1.json())
        assert after > before, f"merge should add records: before={before} after={after}"

    def test_restore_replace_resets(self, client):
        bid = pytest.backup_id
        r = client.post(f"{BASE_URL}/api/backups/{bid}/restore?mode=replace")
        assert r.status_code == 200, r.text
        assert r.json()["mode"] == "replace"
        # Backup had at least 5 records, replace should leave exactly the backup content
        r1 = client.get(f"{BASE_URL}/api/expenses")
        # Only 1 expense was in the backup at creation time
        assert len(r1.json()) == 1

    def test_delete_backup(self, client):
        # Create a temp one to delete
        r = client.post(f"{BASE_URL}/api/backups")
        bid = r.json()["id"]
        r = client.delete(f"{BASE_URL}/api/backups/{bid}")
        assert r.status_code == 200
        # Second delete -> 404
        r = client.delete(f"{BASE_URL}/api/backups/{bid}")
        assert r.status_code == 404

    def test_download_missing_404(self, client):
        r = client.get(f"{BASE_URL}/api/backups/bak_nonexistent/download")
        assert r.status_code == 404


class TestRestoreFile:
    def test_restore_from_file_merge(self, client):
        payload = {
            "version": 1,
            "collections": ["expenses"],
            "payload": {
                "expenses": [
                    {"id": "will-be-replaced", "user_id": "will-be-replaced",
                     "category": "TEST_BAK_uploaded", "description": "from file",
                     "amount": 42, "date": "2026-07-10", "status": "paid",
                     "currency": "TRY", "vat_rate": 20}
                ]
            }
        }
        files = {"file": ("bak.json", json.dumps(payload).encode("utf-8"), "application/json")}
        r = client.post(f"{BASE_URL}/api/backups/restore-file?mode=merge", files=files)
        assert r.status_code == 200, r.text
        assert r.json()["restored"] == 1
        # Verify persisted with new UUID
        r2 = client.get(f"{BASE_URL}/api/expenses")
        assert any(e["category"] == "TEST_BAK_uploaded" for e in r2.json())
        for e in r2.json():
            if e["category"] == "TEST_BAK_uploaded":
                assert e["id"] != "will-be-replaced"

    def test_restore_from_file_invalid_json_400(self, client):
        files = {"file": ("bad.json", b"{not valid json", "application/json")}
        r = client.post(f"{BASE_URL}/api/backups/restore-file", files=files)
        assert r.status_code == 400

    def test_restore_from_file_wrong_version_400(self, client):
        files = {"file": ("v2.json", json.dumps({"version": 2, "payload": {}}).encode(), "application/json")}
        r = client.post(f"{BASE_URL}/api/backups/restore-file", files=files)
        assert r.status_code == 400


class TestWorkspaceIsolation:
    def test_other_workspace_backup_isolated(self, client):
        # Create a second user + workspace
        from pymongo import MongoClient
        mongo = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        dbn = os.environ.get("DB_NAME", "test_database")
        d = mongo[dbn]
        import time as _t
        uid2 = f"test-bak2-{int(_t.time()*1000)}"
        tok2 = f"test_session_bak2_{int(_t.time()*1000)}"
        from datetime import datetime, timedelta
        d.users.insert_one({"user_id": uid2, "email": f"{uid2}@x.com", "name": "U2",
                            "picture": "x", "created_at": datetime.utcnow()})
        d.user_sessions.insert_one({"user_id": uid2, "session_token": tok2,
                                     "expires_at": datetime.utcnow() + timedelta(days=1),
                                     "created_at": datetime.utcnow()})
        s2 = requests.Session()
        s2.headers.update({"Authorization": f"Bearer {tok2}"})
        # user2 should see 0 backups even though user1 has some
        r = s2.get(f"{BASE_URL}/api/backups")
        assert r.status_code == 200
        assert r.json() == []
        # user2 cannot download user1's backup
        r = s2.get(f"{BASE_URL}/api/backups/{pytest.backup_id}/download")
        assert r.status_code == 404
        # Cleanup
        d.user_sessions.delete_one({"session_token": tok2})
        d.users.delete_one({"user_id": uid2})


class TestRetention:
    def test_only_10_kept(self, client):
        # Delete existing backups first for a clean count
        r = client.get(f"{BASE_URL}/api/backups")
        for b in r.json():
            client.delete(f"{BASE_URL}/api/backups/{b['id']}")
        # Create 12
        for i in range(12):
            r = client.post(f"{BASE_URL}/api/backups")
            assert r.status_code == 200
        r = client.get(f"{BASE_URL}/api/backups")
        assert len(r.json()) == 10


class TestSchedulerRegistered:
    def test_scheduler_log_line(self):
        # Verify the backend log contains scheduler registration line
        import subprocess
        out = subprocess.run(
            ["bash", "-lc", "cat /var/log/supervisor/backend.*.log | grep -E 'Weekly backups' | tail -5"],
            capture_output=True, text=True,
        )
        assert "Weekly backups: Sun 03:00 UTC" in (out.stdout + out.stderr), out.stdout
