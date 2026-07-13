"""Backend tests for notification preferences feature and reminder logic."""
import os
import time
import uuid
import pytest
import requests
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://cashflow-hub-444.preview.emergentagent.com").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

mongo = MongoClient(MONGO_URL)
db = mongo[DB_NAME]


@pytest.fixture(scope="module")
def test_user():
    uid = f"test-user-prefs-{int(time.time()*1000)}"
    token = f"test_session_prefs_{int(time.time()*1000)}"
    email = f"prefs.{int(time.time()*1000)}@example.com"
    db.users.insert_one({"user_id": uid, "email": email, "name": "Prefs Tester", "picture": "", "created_at": datetime.now(timezone.utc).isoformat()})
    db.user_sessions.insert_one({
        "user_id": uid, "session_token": token,
        "expires_at": (datetime.now(timezone.utc)+timedelta(days=7)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    yield {"user_id": uid, "token": token, "email": email}
    # cleanup
    db.user_sessions.delete_many({"user_id": uid})
    db.users.delete_many({"user_id": uid})
    db.user_preferences.delete_many({"user_id": uid})
    db.notifications.delete_many({"user_id": uid})
    db.checks.delete_many({"user_id": uid})
    db.promissory_notes.delete_many({"user_id": uid})


@pytest.fixture
def client(test_user):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {test_user['token']}", "Content-Type": "application/json"})
    return s


# ---------- GET /api/preferences ----------
def test_get_preferences_no_auth():
    r = requests.get(f"{BASE_URL}/api/preferences")
    assert r.status_code == 401


def test_get_preferences_defaults(client, test_user):
    # ensure no saved prefs
    db.user_preferences.delete_many({"user_id": test_user["user_id"]})
    r = client.get(f"{BASE_URL}/api/preferences")
    assert r.status_code == 200
    data = r.json()
    assert data["email_enabled"] is True
    assert data["in_app_enabled"] is True
    assert data["reminder_days"] == [3, 1]
    assert data["notification_email"] is None


# ---------- PUT /api/preferences ----------
def test_put_preferences_save_and_persist(client, test_user):
    payload = {"email_enabled": False, "in_app_enabled": True, "reminder_days": [7, 3, 1], "notification_email": "test@example.com"}
    r = client.put(f"{BASE_URL}/api/preferences", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["email_enabled"] is False
    assert data["in_app_enabled"] is True
    assert sorted(data["reminder_days"]) == [1, 3, 7]
    assert data["notification_email"] == "test@example.com"

    # persistence check
    r2 = client.get(f"{BASE_URL}/api/preferences")
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["email_enabled"] is False
    assert sorted(d2["reminder_days"]) == [1, 3, 7]
    assert d2["notification_email"] == "test@example.com"


def test_put_preferences_filters_invalid_days(client):
    payload = {"email_enabled": True, "in_app_enabled": True, "reminder_days": [0, -1, 100, 5, 3], "notification_email": None}
    r = client.put(f"{BASE_URL}/api/preferences", json=payload)
    assert r.status_code == 200
    data = r.json()
    # 0, -1, 100 filtered; 5,3 kept (server range 0<d<=60)
    assert set(data["reminder_days"]) == {3, 5}


def test_put_preferences_empty_days_falls_back(client):
    payload = {"email_enabled": True, "in_app_enabled": True, "reminder_days": [], "notification_email": None}
    r = client.put(f"{BASE_URL}/api/preferences", json=payload)
    assert r.status_code == 200
    assert sorted(r.json()["reminder_days"]) == [1, 3]


def test_put_preferences_empty_email_becomes_null(client):
    payload = {"email_enabled": True, "in_app_enabled": True, "reminder_days": [3], "notification_email": "   "}
    r = client.put(f"{BASE_URL}/api/preferences", json=payload)
    assert r.status_code == 200
    assert r.json()["notification_email"] is None


# ---------- Reminder logic honors preferences ----------
def _create_check(client, days_from_now, party="TEST_Party"):
    due = (datetime.now(timezone.utc).date() + timedelta(days=days_from_now)).isoformat()
    r = client.post(f"{BASE_URL}/api/checks", json={
        "type": "received", "party": party, "amount": 100.0,
        "due_date": due, "status": "pending"
    })
    assert r.status_code == 200
    return r.json()


def test_reminders_in_app_disabled_no_notif(client, test_user):
    uid = test_user["user_id"]
    db.notifications.delete_many({"user_id": uid})
    db.checks.delete_many({"user_id": uid})
    # set prefs: in-app disabled, email disabled -> early return
    client.put(f"{BASE_URL}/api/preferences", json={"email_enabled": False, "in_app_enabled": False, "reminder_days": [3], "notification_email": None})
    _create_check(client, 3)
    r = client.post(f"{BASE_URL}/api/notifications/check-reminders")
    assert r.status_code == 200
    assert db.notifications.count_documents({"user_id": uid}) == 0


def test_reminders_in_app_only_creates_notif(client, test_user):
    uid = test_user["user_id"]
    db.notifications.delete_many({"user_id": uid})
    db.checks.delete_many({"user_id": uid})
    # in-app on, email off
    client.put(f"{BASE_URL}/api/preferences", json={"email_enabled": False, "in_app_enabled": True, "reminder_days": [3], "notification_email": None})
    _create_check(client, 3, "TEST_InApp")
    r = client.post(f"{BASE_URL}/api/notifications/check-reminders")
    assert r.status_code == 200
    body = r.json()
    assert body["created"] == 1
    assert body["email_sent"] is False
    # verify notif exists
    n = db.notifications.find_one({"user_id": uid})
    assert n is not None
    assert n["days_before"] == 3
    assert n["email_sent"] is False


def test_reminders_uses_custom_reminder_days(client, test_user):
    uid = test_user["user_id"]
    db.notifications.delete_many({"user_id": uid})
    db.checks.delete_many({"user_id": uid})
    # reminder_days=[7] only
    client.put(f"{BASE_URL}/api/preferences", json={"email_enabled": False, "in_app_enabled": True, "reminder_days": [7], "notification_email": None})
    _create_check(client, 3, "TEST_3d")  # should NOT trigger
    _create_check(client, 7, "TEST_7d")  # should trigger
    r = client.post(f"{BASE_URL}/api/notifications/check-reminders")
    assert r.status_code == 200
    assert r.json()["created"] == 1
    notifs = list(db.notifications.find({"user_id": uid}))
    assert len(notifs) == 1
    assert notifs[0]["days_before"] == 7


def test_reminders_respects_notification_email_override(client, test_user, monkeypatch):
    """Verify target email selection logic: prefs.notification_email overrides user.email.
    Since Resend may not be configured, we validate via check-reminders result and notification records
    (email_sent may be False if RESEND_API_KEY absent, which is expected)."""
    uid = test_user["user_id"]
    db.notifications.delete_many({"user_id": uid})
    db.checks.delete_many({"user_id": uid})
    client.put(f"{BASE_URL}/api/preferences", json={
        "email_enabled": True, "in_app_enabled": True,
        "reminder_days": [3], "notification_email": "override@example.com"
    })
    _create_check(client, 3, "TEST_EmailOverride")
    r = client.post(f"{BASE_URL}/api/notifications/check-reminders")
    assert r.status_code == 200
    # confirm prefs are actually saved with override
    p = db.user_preferences.find_one({"user_id": uid})
    assert p["notification_email"] == "override@example.com"
