"""Iteration 3: Date range filters + PDF report tests."""
import os
import pytest
import requests
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://cashflow-hub-444.preview.emergentagent.com").rstrip("/")
TOKEN = os.environ.get("TEST_SESSION_TOKEN")


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def seed(client):
    """Seed incomes, expenses, checks, notes across dates."""
    today = datetime.now(timezone.utc).date()
    dates = {
        "old": (today - timedelta(days=120)).isoformat(),
        "recent": (today - timedelta(days=10)).isoformat(),
        "future": (today + timedelta(days=20)).isoformat(),
    }
    ids = {"expenses": [], "incomes": [], "checks": [], "notes": []}
    # expenses / incomes on 'date'
    for label, d in [("old", dates["old"]), ("recent", dates["recent"])]:
        r = client.post(f"{BASE_URL}/api/expenses", json={
            "category": "Test", "description": f"TEST_exp_{label}", "amount": 100.0, "date": d
        })
        assert r.status_code == 200, r.text
        ids["expenses"].append(r.json()["id"])
        r = client.post(f"{BASE_URL}/api/incomes", json={
            "source": "TestSrc", "description": f"TEST_inc_{label}", "amount": 200.0, "date": d
        })
        assert r.status_code == 200
        ids["incomes"].append(r.json()["id"])
    # checks / notes on due_date
    for label, d in [("recent", dates["recent"]), ("future", dates["future"])]:
        r = client.post(f"{BASE_URL}/api/checks", json={
            "type": "received", "party": f"TEST_chk_{label}", "amount": 300.0, "due_date": d, "status": "pending"
        })
        assert r.status_code == 200
        ids["checks"].append(r.json()["id"])
        r = client.post(f"{BASE_URL}/api/promissory-notes", json={
            "type": "issued", "party": f"TEST_note_ç_ğ_ş_{label}", "amount": 400.0, "due_date": d, "status": "pending"
        })
        assert r.status_code == 200
        ids["notes"].append(r.json()["id"])
    yield {"ids": ids, "dates": dates}
    # cleanup
    for i in ids["expenses"]:
        client.delete(f"{BASE_URL}/api/expenses/{i}")
    for i in ids["incomes"]:
        client.delete(f"{BASE_URL}/api/incomes/{i}")
    for i in ids["checks"]:
        client.delete(f"{BASE_URL}/api/checks/{i}")
    for i in ids["notes"]:
        client.delete(f"{BASE_URL}/api/promissory-notes/{i}")


class TestDateRangeFilter:
    def test_expenses_no_filter(self, client, seed):
        r = client.get(f"{BASE_URL}/api/expenses")
        assert r.status_code == 200
        descs = [e["description"] for e in r.json()]
        assert any("TEST_exp_old" in d for d in descs)
        assert any("TEST_exp_recent" in d for d in descs)

    def test_expenses_start_only(self, client, seed):
        start = (datetime.now(timezone.utc).date() - timedelta(days=30)).isoformat()
        r = client.get(f"{BASE_URL}/api/expenses", params={"start_date": start})
        assert r.status_code == 200
        descs = [e["description"] for e in r.json()]
        assert any("TEST_exp_recent" in d for d in descs)
        assert not any("TEST_exp_old" in d for d in descs)

    def test_expenses_end_only(self, client, seed):
        end = (datetime.now(timezone.utc).date() - timedelta(days=60)).isoformat()
        r = client.get(f"{BASE_URL}/api/expenses", params={"end_date": end})
        assert r.status_code == 200
        descs = [e["description"] for e in r.json()]
        assert any("TEST_exp_old" in d for d in descs)
        assert not any("TEST_exp_recent" in d for d in descs)

    def test_expenses_range(self, client, seed):
        today = datetime.now(timezone.utc).date()
        start = (today - timedelta(days=30)).isoformat()
        end = today.isoformat()
        r = client.get(f"{BASE_URL}/api/expenses", params={"start_date": start, "end_date": end})
        assert r.status_code == 200
        for e in r.json():
            assert start <= e["date"] <= end

    def test_incomes_range(self, client, seed):
        today = datetime.now(timezone.utc).date()
        start = (today - timedelta(days=30)).isoformat()
        r = client.get(f"{BASE_URL}/api/incomes", params={"start_date": start})
        assert r.status_code == 200
        for i in r.json():
            assert i["date"] >= start

    def test_checks_due_date_filter(self, client, seed):
        today = datetime.now(timezone.utc).date()
        start = today.isoformat()
        r = client.get(f"{BASE_URL}/api/checks", params={"start_date": start})
        assert r.status_code == 200
        for c in r.json():
            assert c["due_date"] >= start

    def test_notes_due_date_filter(self, client, seed):
        today = datetime.now(timezone.utc).date()
        end = today.isoformat()
        r = client.get(f"{BASE_URL}/api/promissory-notes", params={"end_date": end})
        assert r.status_code == 200
        for n in r.json():
            assert n["due_date"] <= end


class TestPdfReport:
    def test_pdf_default_current_month(self, client, seed):
        r = client.get(f"{BASE_URL}/api/reports/pdf")
        assert r.status_code == 200
        assert "application/pdf" in r.headers.get("content-type", "")
        assert r.content[:4] == b"%PDF"
        assert len(r.content) > 500

    def test_pdf_custom_range(self, client, seed):
        today = datetime.now(timezone.utc).date()
        start = (today - timedelta(days=60)).isoformat()
        end = today.isoformat()
        r = client.get(f"{BASE_URL}/api/reports/pdf", params={"start_date": start, "end_date": end})
        assert r.status_code == 200
        assert r.content.startswith(b"%PDF")
        # Filename in header uses dates
        cd = r.headers.get("content-disposition", "")
        assert start in cd and end in cd

    def test_pdf_empty_period(self, client, seed):
        # Range with no data
        r = client.get(f"{BASE_URL}/api/reports/pdf", params={
            "start_date": "2000-01-01", "end_date": "2000-01-31"
        })
        assert r.status_code == 200
        assert r.content.startswith(b"%PDF")

    def test_pdf_turkish_chars(self, client, seed):
        # The seeded notes contain ç, ğ, ş - if font missing this would 500
        today = datetime.now(timezone.utc).date()
        start = today.isoformat()
        end = (today + timedelta(days=60)).isoformat()
        r = client.get(f"{BASE_URL}/api/reports/pdf", params={"start_date": start, "end_date": end})
        assert r.status_code == 200
        assert r.content.startswith(b"%PDF")


class TestAuth:
    def test_pdf_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/reports/pdf")
        assert r.status_code == 401
