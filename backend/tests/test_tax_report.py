"""Iteration 6: KDV Tax Report tests."""
import os
import pytest
import requests
from datetime import datetime

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
TOKEN = os.environ.get("TEST_SESSION_TOKEN")


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def seed(client):
    """Seed july-2026 records with different vat rates."""
    created = []
    # Income: 17500 gross @ 20% (vat=2916.67, net=14583.33)
    r = client.post(f"{BASE_URL}/api/incomes", json={
        "source": "TEST_TAX_income_20", "description": "TEST_TAX", "amount": 17500,
        "vat_rate": 20, "date": "2026-07-15", "status": "received"
    })
    assert r.status_code in (200, 201), r.text
    created.append(("incomes", r.json()["id"]))

    # Expense 1: 1100 gross @ 10% (vat=100, net=1000)
    r = client.post(f"{BASE_URL}/api/expenses", json={
        "category": "TEST_TAX_exp_10", "description": "TEST_TAX", "amount": 1100,
        "vat_rate": 10, "date": "2026-07-05", "status": "paid"
    })
    assert r.status_code in (200, 201), r.text
    created.append(("expenses", r.json()["id"]))

    # Expense 2: 6000 gross @ 20% (vat=1000, net=5000)
    r = client.post(f"{BASE_URL}/api/expenses", json={
        "category": "TEST_TAX_exp_20", "description": "TEST_TAX", "amount": 6000,
        "vat_rate": 20, "date": "2026-07-20", "status": "paid"
    })
    assert r.status_code in (200, 201), r.text
    created.append(("expenses", r.json()["id"]))

    # Expense 3 (no vat_rate, uses default 20): 1200 gross -> vat=200
    r = client.post(f"{BASE_URL}/api/expenses", json={
        "category": "TEST_TAX_default", "description": "TEST_TAX", "amount": 1200,
        "date": "2026-07-25", "status": "paid"
    })
    assert r.status_code in (200, 201), r.text
    created.append(("expenses", r.json()["id"]))

    yield
    # Cleanup
    for coll, _id in created:
        client.delete(f"{BASE_URL}/api/{coll}/{_id}")


class TestTaxReport:
    def test_default_vat_on_create(self, client):
        r = client.post(f"{BASE_URL}/api/expenses", json={
            "category": "TEST_TAX_defcheck", "description": "TEST_TAX", "amount": 500, "date": "2026-07-01"
        })
        assert r.status_code in (200, 201), r.text
        body = r.json()
        assert body.get("vat_rate") == 20.0
        client.delete(f"{BASE_URL}/api/expenses/{body['id']}")

    def test_monthly_period(self, client, seed):
        r = client.get(f"{BASE_URL}/api/reports/tax", params={"period": "2026-07"})
        assert r.status_code == 200
        d = r.json()
        assert d["start_date"] == "2026-07-01"
        assert d["end_date"] == "2026-07-31"
        # Income totals
        assert d["income"]["total_gross"] == 17500.0
        assert d["income"]["total_vat"] == 2916.67
        assert d["income"]["total_net"] == 14583.33
        # Expense totals: gross = 1100+6000+1200=8300; vat=100+1000+200=1300
        assert d["expense"]["total_gross"] == 8300.0
        assert d["expense"]["total_vat"] == 1300.0
        # Payable vat
        assert d["payable_vat"] == round(2916.67 - 1300.0, 2)
        assert d["vat_status"] == "pay"
        # Breakdown for expenses should have rates 10 and 20
        rates = {b["rate"] for b in d["expense"]["breakdown"]}
        assert 10.0 in rates and 20.0 in rates
        b10 = next(b for b in d["expense"]["breakdown"] if b["rate"] == 10.0)
        assert b10["vat"] == 100.0 and b10["net"] == 1000.0
        b20 = next(b for b in d["expense"]["breakdown"] if b["rate"] == 20.0)
        # 6000+1200=7200 @ 20% -> vat=1200, net=6000
        assert b20["gross"] == 7200.0
        assert b20["vat"] == 1200.0

    def test_quarterly_period(self, client, seed):
        r = client.get(f"{BASE_URL}/api/reports/tax", params={"period": "2026-Q3"})
        assert r.status_code == 200
        d = r.json()
        assert d["start_date"] == "2026-07-01"
        assert d["end_date"] == "2026-09-30"
        assert d["income"]["total_gross"] >= 17500.0

    def test_invalid_period(self, client):
        r = client.get(f"{BASE_URL}/api/reports/tax", params={"period": "bogus"})
        assert r.status_code == 400

    def test_custom_range(self, client, seed):
        r = client.get(f"{BASE_URL}/api/reports/tax",
                       params={"start_date": "2026-07-01", "end_date": "2026-07-31"})
        assert r.status_code == 200
        d = r.json()
        assert d["income"]["total_gross"] == 17500.0

    def test_refund_status(self, client):
        # Create expense-only period range where expense_vat > income_vat
        r = client.post(f"{BASE_URL}/api/expenses", json={
            "category": "TEST_TAX_refund", "description": "TEST_TAX", "amount": 12000, "vat_rate": 20,
            "date": "2020-01-15", "status": "paid"
        })
        eid = r.json()["id"]
        rep = client.get(f"{BASE_URL}/api/reports/tax", params={"period": "2020-01"})
        assert rep.status_code == 200
        d = rep.json()
        assert d["expense"]["total_vat"] > 0
        assert d["vat_status"] == "refund"
        assert d["payable_vat"] < 0
        client.delete(f"{BASE_URL}/api/expenses/{eid}")

    def test_pdf_export(self, client, seed):
        r = client.get(f"{BASE_URL}/api/reports/tax/pdf", params={"period": "2026-07"})
        assert r.status_code == 200
        assert "application/pdf" in r.headers.get("content-type", "").lower()
        assert r.content[:4] == b"%PDF"

    def test_xlsx_export(self, client, seed):
        r = client.get(f"{BASE_URL}/api/reports/tax/xlsx", params={"period": "2026-07"})
        assert r.status_code == 200
        # xlsx = zip -> starts with PK
        assert r.content[:2] == b"PK"

    def test_import_template_has_vat_rate(self, client):
        r = client.get(f"{BASE_URL}/api/import/expenses/template")
        assert r.status_code == 200
        # xlsx zip
        assert r.content[:2] == b"PK"
        # Check for vat_rate column via openpyxl
        import io, openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        ws = wb.active
        headers = [c.value for c in next(ws.iter_rows(max_row=1))]
        assert "vat_rate" in headers

    def test_auth_required(self):
        r = requests.get(f"{BASE_URL}/api/reports/tax", params={"period": "2026-07"})
        assert r.status_code == 401
