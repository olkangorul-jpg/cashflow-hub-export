"""Integration tests for automatic bank balance synchronization on expenses/incomes CRUD."""
import asyncio
import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from httpx import AsyncClient, ASGITransport

os.environ.setdefault("MONGO_URL", os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
os.environ.setdefault("DB_NAME", os.environ.get("DB_NAME", "test_database"))

from server import app  # noqa: E402

PREFIX = "TEST_BAL_"


@pytest.fixture(scope="module")
def loop():
    l = asyncio.new_event_loop()
    yield l
    l.close()


@pytest.fixture(scope="module")
def seeded(loop):
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    user_id = f"{PREFIX}owner"
    ws_id = f"{PREFIX}ws"
    session_token = f"{PREFIX}tok"
    acc_id = f"{PREFIX}acc1"

    async def setup():
        # Cleanup
        for coll in ("users", "workspaces", "user_sessions", "bank_accounts", "expenses", "incomes"):
            await db[coll].delete_many({"$or": [
                {"user_id": {"$regex": f"^{PREFIX}"}},
                {"workspace_id": {"$regex": f"^{PREFIX}"}},
                {"id": {"$regex": f"^{PREFIX}"}},
            ]})

        await db.users.insert_one({
            "user_id": user_id, "email": "bal@test.com", "name": "Bal Tester",
            "picture": "", "active_workspace_id": ws_id,
        })
        await db.workspaces.insert_one({
            "workspace_id": ws_id, "name": "Bal WS", "owner_user_id": user_id,
        })
        await db.user_sessions.insert_one({
            "session_token": session_token, "user_id": user_id,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        })
        await db.bank_accounts.insert_one({
            "id": acc_id, "user_id": user_id, "name": "Test Acc", "bank_name": "TestBank",
            "account_number": "", "balance": 100000.0, "currency": "TRY",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    loop.run_until_complete(setup())
    yield {"user_id": user_id, "ws_id": ws_id, "token": session_token, "acc_id": acc_id, "db": db}

    async def teardown():
        for coll in ("users", "workspaces", "user_sessions", "bank_accounts", "expenses", "incomes"):
            await db[coll].delete_many({"$or": [
                {"user_id": {"$regex": f"^{PREFIX}"}},
                {"workspace_id": {"$regex": f"^{PREFIX}"}},
                {"id": {"$regex": f"^{PREFIX}"}},
            ]})
        client.close()

    loop.run_until_complete(teardown())


def _headers(tok):
    return {"Authorization": f"Bearer {tok}"}


async def _get_balance(db, acc_id):
    doc = await db.bank_accounts.find_one({"id": acc_id}, {"_id": 0, "balance": 1})
    return doc["balance"]


def _run(loop, coro):
    return loop.run_until_complete(coro)


def test_expense_create_deducts_balance(loop, seeded):
    async def _t():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/api/expenses",
                json={"category": "Kira", "description": "test kira", "amount": 45000, "vat_rate": 20,
                      "date": "2026-02-14", "bank_account_id": seeded["acc_id"]},
                headers=_headers(seeded["token"]),
            )
            assert r.status_code == 200, r.text
            eid = r.json()["id"]
            bal = await _get_balance(seeded["db"], seeded["acc_id"])
            assert bal == 55000.0, f"expected 55000 got {bal}"
            return eid
    seeded["exp_id"] = _run(loop, _t())


def test_expense_update_amount_adjusts_balance(loop, seeded):
    async def _t():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            # Change from 45000 -> 30000, balance should go from 55000 to 70000
            r = await c.put(
                f"/api/expenses/{seeded['exp_id']}",
                json={"category": "Kira", "description": "test kira", "amount": 30000, "vat_rate": 20,
                      "date": "2026-02-14", "bank_account_id": seeded["acc_id"]},
                headers=_headers(seeded["token"]),
            )
            assert r.status_code == 200, r.text
            bal = await _get_balance(seeded["db"], seeded["acc_id"])
            assert bal == 70000.0, f"expected 70000 got {bal}"
    _run(loop, _t())


def test_expense_delete_refunds_balance(loop, seeded):
    async def _t():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.delete(
                f"/api/expenses/{seeded['exp_id']}",
                headers=_headers(seeded["token"]),
            )
            assert r.status_code == 200, r.text
            bal = await _get_balance(seeded["db"], seeded["acc_id"])
            assert bal == 100000.0, f"expected 100000 got {bal}"
    _run(loop, _t())


def test_income_create_adds_balance(loop, seeded):
    async def _t():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/api/incomes",
                json={"source": "Satış", "description": "test", "amount": 25000, "vat_rate": 20,
                      "date": "2026-02-14", "bank_account_id": seeded["acc_id"]},
                headers=_headers(seeded["token"]),
            )
            assert r.status_code == 200, r.text
            iid = r.json()["id"]
            bal = await _get_balance(seeded["db"], seeded["acc_id"])
            assert bal == 125000.0, f"expected 125000 got {bal}"
            return iid
    seeded["inc_id"] = _run(loop, _t())


def test_income_delete_reverses(loop, seeded):
    async def _t():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.delete(
                f"/api/incomes/{seeded['inc_id']}",
                headers=_headers(seeded["token"]),
            )
            assert r.status_code == 200, r.text
            bal = await _get_balance(seeded["db"], seeded["acc_id"])
            assert bal == 100000.0, f"expected 100000 got {bal}"
    _run(loop, _t())


def test_expense_without_bank_account_does_not_touch_balance(loop, seeded):
    async def _t():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/api/expenses",
                json={"category": "Diğer", "description": "nakit gider", "amount": 5000, "vat_rate": 20,
                      "date": "2026-02-14", "bank_account_id": None},
                headers=_headers(seeded["token"]),
            )
            assert r.status_code == 200, r.text
            bal = await _get_balance(seeded["db"], seeded["acc_id"])
            assert bal == 100000.0, f"balance should be unchanged, got {bal}"
    _run(loop, _t())
