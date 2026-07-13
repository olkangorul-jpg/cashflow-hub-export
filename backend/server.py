from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import os
import io
import csv
import asyncio
import logging
import uuid
import requests
import resend
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal
from datetime import datetime, timezone, timedelta, date

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

# Resend email setup
resend.api_key = os.environ.get("RESEND_API_KEY", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")

app = FastAPI()
api_router = APIRouter(prefix="/api")

# ---------------- Models ----------------
class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BankAccount(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    name: str
    bank_name: str
    account_number: Optional[str] = ""
    balance: float = 0.0
    currency: str = "TRY"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BankAccountCreate(BaseModel):
    name: str
    bank_name: str
    account_number: Optional[str] = ""
    balance: float = 0.0
    currency: str = "TRY"


class Check(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    type: Literal["received", "issued"]
    party: str  # payer if received, payee if issued
    amount: float
    due_date: str  # ISO date
    bank_name: Optional[str] = ""
    check_number: Optional[str] = ""
    status: Literal["pending", "cleared", "bounced"] = "pending"
    notes: Optional[str] = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CheckCreate(BaseModel):
    type: Literal["received", "issued"]
    party: str
    amount: float
    due_date: str
    bank_name: Optional[str] = ""
    check_number: Optional[str] = ""
    status: Literal["pending", "cleared", "bounced"] = "pending"
    notes: Optional[str] = ""


class PromissoryNote(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    type: Literal["received", "issued"]
    party: str
    amount: float
    due_date: str
    status: Literal["pending", "paid", "overdue"] = "pending"
    notes: Optional[str] = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PromissoryNoteCreate(BaseModel):
    type: Literal["received", "issued"]
    party: str
    amount: float
    due_date: str
    status: Literal["pending", "paid", "overdue"] = "pending"
    notes: Optional[str] = ""


class Expense(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    category: str
    description: str
    amount: float
    date: str
    bank_account_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExpenseCreate(BaseModel):
    category: str
    description: str
    amount: float
    date: str
    bank_account_id: Optional[str] = None


class Income(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    source: str
    description: str
    amount: float
    date: str
    bank_account_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class IncomeCreate(BaseModel):
    source: str
    description: str
    amount: float
    date: str
    bank_account_id: Optional[str] = None


# ---------------- Auth Helpers ----------------
async def get_current_user(request: Request) -> User:
    # REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    token = request.cookies.get("session_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    expires_at = session["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")

    user_doc = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
    if not user_doc:
        raise HTTPException(status_code=401, detail="User not found")
    return User(**user_doc)


# ---------------- Auth Routes ----------------
class SessionExchange(BaseModel):
    session_id: str


@api_router.post("/auth/session")
async def create_session(payload: SessionExchange, response: Response):
    # REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    try:
        r = requests.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": payload.session_id},
            timeout=10,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Auth service unreachable: {e}")
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid session_id")
    data = r.json()
    email = data["email"]
    name = data.get("name", email)
    picture = data.get("picture", "")
    session_token = data["session_token"]

    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        await db.users.update_one({"user_id": user_id}, {"$set": {"name": name, "picture": picture}})
    else:
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": user_id, "email": email, "name": name, "picture": picture,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await db.user_sessions.insert_one({
        "user_id": user_id, "session_token": session_token,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    response.set_cookie(
        key="session_token", value=session_token,
        httponly=True, secure=True, samesite="none", path="/",
        max_age=7 * 24 * 60 * 60,
    )
    return {"user_id": user_id, "email": email, "name": name, "picture": picture}


@api_router.get("/auth/me")
async def me(user: User = Depends(get_current_user)):
    return {"user_id": user.user_id, "email": user.email, "name": user.name, "picture": user.picture}


@api_router.post("/auth/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    response.delete_cookie("session_token", path="/")
    return {"ok": True}


# ---------------- Bank Accounts ----------------
@api_router.get("/bank-accounts", response_model=List[BankAccount])
async def list_bank_accounts(user: User = Depends(get_current_user)):
    docs = await db.bank_accounts.find({"user_id": user.user_id}, {"_id": 0}).to_list(1000)
    return [BankAccount(**d) for d in docs]


@api_router.post("/bank-accounts", response_model=BankAccount)
async def create_bank_account(payload: BankAccountCreate, user: User = Depends(get_current_user)):
    obj = BankAccount(user_id=user.user_id, **payload.model_dump())
    d = obj.model_dump()
    d["created_at"] = d["created_at"].isoformat()
    await db.bank_accounts.insert_one(d)
    return obj


@api_router.put("/bank-accounts/{account_id}", response_model=BankAccount)
async def update_bank_account(account_id: str, payload: BankAccountCreate, user: User = Depends(get_current_user)):
    res = await db.bank_accounts.update_one(
        {"id": account_id, "user_id": user.user_id},
        {"$set": payload.model_dump()},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    doc = await db.bank_accounts.find_one({"id": account_id}, {"_id": 0})
    return BankAccount(**doc)


@api_router.delete("/bank-accounts/{account_id}")
async def delete_bank_account(account_id: str, user: User = Depends(get_current_user)):
    await db.bank_accounts.delete_one({"id": account_id, "user_id": user.user_id})
    return {"ok": True}


# ---------------- Checks ----------------
@api_router.get("/checks", response_model=List[Check])
async def list_checks(user: User = Depends(get_current_user)):
    docs = await db.checks.find({"user_id": user.user_id}, {"_id": 0}).sort("due_date", 1).to_list(2000)
    return [Check(**d) for d in docs]


@api_router.post("/checks", response_model=Check)
async def create_check(payload: CheckCreate, user: User = Depends(get_current_user)):
    obj = Check(user_id=user.user_id, **payload.model_dump())
    d = obj.model_dump()
    d["created_at"] = d["created_at"].isoformat()
    await db.checks.insert_one(d)
    return obj


@api_router.put("/checks/{check_id}", response_model=Check)
async def update_check(check_id: str, payload: CheckCreate, user: User = Depends(get_current_user)):
    res = await db.checks.update_one(
        {"id": check_id, "user_id": user.user_id},
        {"$set": payload.model_dump()},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    doc = await db.checks.find_one({"id": check_id}, {"_id": 0})
    return Check(**doc)


@api_router.delete("/checks/{check_id}")
async def delete_check(check_id: str, user: User = Depends(get_current_user)):
    await db.checks.delete_one({"id": check_id, "user_id": user.user_id})
    return {"ok": True}


# ---------------- Promissory Notes ----------------
@api_router.get("/promissory-notes", response_model=List[PromissoryNote])
async def list_notes(user: User = Depends(get_current_user)):
    docs = await db.promissory_notes.find({"user_id": user.user_id}, {"_id": 0}).sort("due_date", 1).to_list(2000)
    return [PromissoryNote(**d) for d in docs]


@api_router.post("/promissory-notes", response_model=PromissoryNote)
async def create_note(payload: PromissoryNoteCreate, user: User = Depends(get_current_user)):
    obj = PromissoryNote(user_id=user.user_id, **payload.model_dump())
    d = obj.model_dump()
    d["created_at"] = d["created_at"].isoformat()
    await db.promissory_notes.insert_one(d)
    return obj


@api_router.put("/promissory-notes/{note_id}", response_model=PromissoryNote)
async def update_note(note_id: str, payload: PromissoryNoteCreate, user: User = Depends(get_current_user)):
    res = await db.promissory_notes.update_one(
        {"id": note_id, "user_id": user.user_id},
        {"$set": payload.model_dump()},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    doc = await db.promissory_notes.find_one({"id": note_id}, {"_id": 0})
    return PromissoryNote(**doc)


@api_router.delete("/promissory-notes/{note_id}")
async def delete_note(note_id: str, user: User = Depends(get_current_user)):
    await db.promissory_notes.delete_one({"id": note_id, "user_id": user.user_id})
    return {"ok": True}


# ---------------- Expenses ----------------
@api_router.get("/expenses", response_model=List[Expense])
async def list_expenses(user: User = Depends(get_current_user)):
    docs = await db.expenses.find({"user_id": user.user_id}, {"_id": 0}).sort("date", -1).to_list(2000)
    return [Expense(**d) for d in docs]


@api_router.post("/expenses", response_model=Expense)
async def create_expense(payload: ExpenseCreate, user: User = Depends(get_current_user)):
    obj = Expense(user_id=user.user_id, **payload.model_dump())
    d = obj.model_dump()
    d["created_at"] = d["created_at"].isoformat()
    await db.expenses.insert_one(d)
    return obj


@api_router.put("/expenses/{expense_id}", response_model=Expense)
async def update_expense(expense_id: str, payload: ExpenseCreate, user: User = Depends(get_current_user)):
    res = await db.expenses.update_one(
        {"id": expense_id, "user_id": user.user_id},
        {"$set": payload.model_dump()},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    doc = await db.expenses.find_one({"id": expense_id}, {"_id": 0})
    return Expense(**doc)


@api_router.delete("/expenses/{expense_id}")
async def delete_expense(expense_id: str, user: User = Depends(get_current_user)):
    await db.expenses.delete_one({"id": expense_id, "user_id": user.user_id})
    return {"ok": True}


# ---------------- Incomes ----------------
@api_router.get("/incomes", response_model=List[Income])
async def list_incomes(user: User = Depends(get_current_user)):
    docs = await db.incomes.find({"user_id": user.user_id}, {"_id": 0}).sort("date", -1).to_list(2000)
    return [Income(**d) for d in docs]


@api_router.post("/incomes", response_model=Income)
async def create_income(payload: IncomeCreate, user: User = Depends(get_current_user)):
    obj = Income(user_id=user.user_id, **payload.model_dump())
    d = obj.model_dump()
    d["created_at"] = d["created_at"].isoformat()
    await db.incomes.insert_one(d)
    return obj


@api_router.put("/incomes/{income_id}", response_model=Income)
async def update_income(income_id: str, payload: IncomeCreate, user: User = Depends(get_current_user)):
    res = await db.incomes.update_one(
        {"id": income_id, "user_id": user.user_id},
        {"$set": payload.model_dump()},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    doc = await db.incomes.find_one({"id": income_id}, {"_id": 0})
    return Income(**doc)


@api_router.delete("/incomes/{income_id}")
async def delete_income(income_id: str, user: User = Depends(get_current_user)):
    await db.incomes.delete_one({"id": income_id, "user_id": user.user_id})
    return {"ok": True}


# ---------------- Dashboard / Analytics ----------------
@api_router.get("/dashboard/summary")
async def dashboard_summary(user: User = Depends(get_current_user)):
    uid = user.user_id
    accounts = await db.bank_accounts.find({"user_id": uid}, {"_id": 0}).to_list(1000)
    total_balance = sum(a.get("balance", 0.0) for a in accounts)

    checks = await db.checks.find({"user_id": uid}, {"_id": 0}).to_list(2000)
    notes = await db.promissory_notes.find({"user_id": uid}, {"_id": 0}).to_list(2000)
    expenses = await db.expenses.find({"user_id": uid}, {"_id": 0}).to_list(2000)
    incomes = await db.incomes.find({"user_id": uid}, {"_id": 0}).to_list(2000)

    now = datetime.now(timezone.utc).date()
    horizon = now + timedelta(days=30)

    def within(d):
        try:
            return now <= datetime.fromisoformat(d).date() <= horizon
        except Exception:
            return False

    upcoming_incoming = sum(
        c["amount"] for c in checks if c["type"] == "received" and c["status"] == "pending" and within(c["due_date"])
    ) + sum(
        n["amount"] for n in notes if n["type"] == "received" and n["status"] == "pending" and within(n["due_date"])
    )
    upcoming_outgoing = sum(
        c["amount"] for c in checks if c["type"] == "issued" and c["status"] == "pending" and within(c["due_date"])
    ) + sum(
        n["amount"] for n in notes if n["type"] == "issued" and n["status"] == "pending" and within(n["due_date"])
    )

    # Monthly cash flow (last 6 months)
    months = []
    today = datetime.now(timezone.utc).date().replace(day=1)
    for i in range(5, -1, -1):
        y = today.year
        m = today.month - i
        while m <= 0:
            m += 12
            y -= 1
        months.append((y, m))

    def key_of(iso: str):
        try:
            dt = datetime.fromisoformat(iso).date()
            return (dt.year, dt.month)
        except Exception:
            return None

    monthly = []
    tr_month_names = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]
    for (y, m) in months:
        inc = sum(i["amount"] for i in incomes if key_of(i["date"]) == (y, m))
        exp = sum(e["amount"] for e in expenses if key_of(e["date"]) == (y, m))
        monthly.append({
            "month": f"{tr_month_names[m-1]} {str(y)[-2:]}",
            "gelir": round(inc, 2),
            "gider": round(exp, 2),
            "net": round(inc - exp, 2),
        })

    # Expense category breakdown (current month)
    cur = (datetime.now(timezone.utc).year, datetime.now(timezone.utc).month)
    cat = {}
    for e in expenses:
        if key_of(e["date"]) == cur:
            cat[e["category"]] = cat.get(e["category"], 0) + e["amount"]
    categories = [{"name": k, "value": round(v, 2)} for k, v in cat.items()]

    # Upcoming payments list (next 30 days), merged from checks and notes
    upcoming = []
    for c in checks:
        if c["status"] == "pending" and within(c["due_date"]):
            upcoming.append({
                "id": c["id"], "kind": "check", "type": c["type"],
                "party": c["party"], "amount": c["amount"], "due_date": c["due_date"],
            })
    for n in notes:
        if n["status"] == "pending" and within(n["due_date"]):
            upcoming.append({
                "id": n["id"], "kind": "note", "type": n["type"],
                "party": n["party"], "amount": n["amount"], "due_date": n["due_date"],
            })
    upcoming.sort(key=lambda x: x["due_date"])

    # This month totals
    month_income = sum(i["amount"] for i in incomes if key_of(i["date"]) == cur)
    month_expense = sum(e["amount"] for e in expenses if key_of(e["date"]) == cur)

    return {
        "total_balance": round(total_balance, 2),
        "upcoming_incoming": round(upcoming_incoming, 2),
        "upcoming_outgoing": round(upcoming_outgoing, 2),
        "month_income": round(month_income, 2),
        "month_expense": round(month_expense, 2),
        "monthly": monthly,
        "categories": categories,
        "upcoming": upcoming[:20],
        "accounts_count": len(accounts),
    }


# ---------------- CSV Export ----------------
def _stream_csv(rows: List[dict], headers: List[str], filename: str):
    buf = io.StringIO()
    buf.write("\ufeff")  # BOM for Excel Turkish support
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({h: r.get(h, "") for h in headers})
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api_router.get("/export/checks")
async def export_checks(user: User = Depends(get_current_user)):
    docs = await db.checks.find({"user_id": user.user_id}, {"_id": 0}).to_list(5000)
    return _stream_csv(docs, ["type", "party", "amount", "due_date", "bank_name", "check_number", "status", "notes"], "cekler.csv")


@api_router.get("/export/promissory-notes")
async def export_notes(user: User = Depends(get_current_user)):
    docs = await db.promissory_notes.find({"user_id": user.user_id}, {"_id": 0}).to_list(5000)
    return _stream_csv(docs, ["type", "party", "amount", "due_date", "status", "notes"], "senetler.csv")


@api_router.get("/export/expenses")
async def export_expenses(user: User = Depends(get_current_user)):
    docs = await db.expenses.find({"user_id": user.user_id}, {"_id": 0}).to_list(5000)
    return _stream_csv(docs, ["category", "description", "amount", "date", "bank_account_id"], "giderler.csv")


@api_router.get("/export/incomes")
async def export_incomes(user: User = Depends(get_current_user)):
    docs = await db.incomes.find({"user_id": user.user_id}, {"_id": 0}).to_list(5000)
    return _stream_csv(docs, ["source", "description", "amount", "date", "bank_account_id"], "gelirler.csv")


@api_router.get("/")
async def root():
    return {"message": "Nakit Akış API"}


# ---------------- Notifications & Reminders ----------------
class Notification(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    user_id: str
    title: str
    body: str
    kind: str  # check / note
    item_id: Optional[str] = None
    due_date: Optional[str] = None
    days_before: Optional[int] = None
    read: bool = False
    email_sent: bool = False
    created_at: datetime


def _render_email_html(user_name: str, items: List[dict]) -> str:
    rows = ""
    tr_type = {"received": "Alacak", "issued": "Borç"}
    for it in items:
        kind = "Çek" if it["kind"] == "check" else "Senet"
        color = "#991B1B" if it["type"] == "issued" else "#166534"
        rows += f"""
        <tr>
          <td style="padding:12px;border-bottom:1px solid #E2E8F0;font-family:Arial,sans-serif;font-size:14px;">
            <strong>{it['party']}</strong><br/>
            <span style="color:#64748B;font-size:12px;">{kind} · {tr_type.get(it['type'], it['type'])}</span>
          </td>
          <td style="padding:12px;border-bottom:1px solid #E2E8F0;font-family:Arial,sans-serif;font-size:13px;color:#0F172A;">
            {it['due_date']}<br/>
            <span style="color:#B45309;font-size:12px;">{it['days_before']} gün kaldı</span>
          </td>
          <td style="padding:12px;border-bottom:1px solid #E2E8F0;font-family:Arial,sans-serif;font-size:14px;text-align:right;color:{color};font-weight:600;">
            {'-' if it['type']=='issued' else '+'}{it['amount']:,.2f} ₺
          </td>
        </tr>
        """
    return f"""
    <!DOCTYPE html>
    <html><body style="margin:0;background:#F8F9FA;padding:24px;font-family:Arial,sans-serif;">
      <table role="presentation" width="100%" style="max-width:600px;margin:0 auto;background:#fff;border:1px solid #E2E8F0;border-radius:6px;">
        <tr>
          <td style="padding:24px;border-bottom:1px solid #E2E8F0;">
            <h1 style="margin:0;font-size:20px;color:#0F172A;">Yaklaşan Ödemeler</h1>
            <p style="margin:6px 0 0;color:#64748B;font-size:14px;">Merhaba {user_name}, aşağıdaki ödemelerinizin vadesi yaklaşıyor.</p>
          </td>
        </tr>
        <tr>
          <td style="padding:0 24px;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;margin:12px 0;">
              {rows}
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:16px 24px;background:#F8F9FA;border-top:1px solid #E2E8F0;border-radius:0 0 6px 6px;">
            <p style="margin:0;font-size:12px;color:#64748B;">Bu bildirim Nakit Akış Yönetim uygulaması tarafından otomatik olarak gönderildi.</p>
          </td>
        </tr>
      </table>
    </body></html>
    """


async def _send_email(to: str, subject: str, html: str) -> bool:
    if not resend.api_key:
        logger.warning("RESEND_API_KEY not set - skipping email")
        return False
    try:
        params = {"from": SENDER_EMAIL, "to": [to], "subject": subject, "html": html}
        await asyncio.to_thread(resend.Emails.send, params)
        return True
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return False


REMINDER_DAYS = [3, 1]  # days before due to remind


async def _run_reminders_for_user(user_doc: dict):
    uid = user_doc["user_id"]
    today = datetime.now(timezone.utc).date()
    checks = await db.checks.find({"user_id": uid, "status": "pending"}, {"_id": 0}).to_list(2000)
    notes = await db.promissory_notes.find({"user_id": uid, "status": "pending"}, {"_id": 0}).to_list(2000)

    triggered = []
    for it in checks:
        it["_kind"] = "check"
    for it in notes:
        it["_kind"] = "note"
    for it in checks + notes:
        try:
            due = datetime.fromisoformat(it["due_date"]).date()
        except Exception:
            continue
        delta = (due - today).days
        if delta in REMINDER_DAYS:
            # dedupe: one notification per (item, days_before)
            key = {"user_id": uid, "item_id": it["id"], "days_before": delta, "kind": it["_kind"]}
            existing = await db.notifications.find_one(key, {"_id": 0})
            if existing:
                continue
            title = f"{'Çek' if it['_kind']=='check' else 'Senet'} vadesi {delta} gün kaldı"
            kind_label = "Alacak" if it["type"] == "received" else "Borç"
            body = f"{it['party']} · {kind_label} · {it['amount']:.2f} ₺ · Vade: {it['due_date']}"
            notif = {
                "id": str(uuid.uuid4()),
                "user_id": uid,
                "title": title,
                "body": body,
                "kind": it["_kind"],
                "item_id": it["id"],
                "due_date": it["due_date"],
                "days_before": delta,
                "read": False,
                "email_sent": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.notifications.insert_one(notif)
            triggered.append({**it, "kind": it["_kind"], "days_before": delta})

    email_sent = False
    if triggered and user_doc.get("email"):
        html = _render_email_html(user_doc.get("name") or "Kullanıcı", triggered)
        email_sent = await _send_email(
            user_doc["email"],
            f"Nakit Akış — {len(triggered)} yaklaşan ödeme",
            html,
        )
        if email_sent:
            item_ids = [t["id"] for t in triggered]
            await db.notifications.update_many(
                {"user_id": uid, "item_id": {"$in": item_ids}, "email_sent": False},
                {"$set": {"email_sent": True}},
            )
    return {"created": len(triggered), "email_sent": email_sent}


async def _run_reminders_all_users():
    logger.info("Running daily reminder check...")
    users = await db.users.find({}, {"_id": 0}).to_list(10000)
    total = 0
    for u in users:
        try:
            r = await _run_reminders_for_user(u)
            total += r["created"]
        except Exception as e:
            logger.error(f"Reminder failed for user {u.get('user_id')}: {e}")
    logger.info(f"Reminder check done. {total} notifications created.")
    return total


@api_router.get("/notifications", response_model=List[Notification])
async def list_notifications(user: User = Depends(get_current_user)):
    docs = await db.notifications.find({"user_id": user.user_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    for d in docs:
        if isinstance(d.get("created_at"), str):
            d["created_at"] = datetime.fromisoformat(d["created_at"])
    return [Notification(**d) for d in docs]


@api_router.get("/notifications/unread-count")
async def unread_count(user: User = Depends(get_current_user)):
    count = await db.notifications.count_documents({"user_id": user.user_id, "read": False})
    return {"count": count}


@api_router.post("/notifications/{notif_id}/read")
async def mark_read(notif_id: str, user: User = Depends(get_current_user)):
    await db.notifications.update_one({"id": notif_id, "user_id": user.user_id}, {"$set": {"read": True}})
    return {"ok": True}


@api_router.post("/notifications/mark-all-read")
async def mark_all_read(user: User = Depends(get_current_user)):
    await db.notifications.update_many({"user_id": user.user_id, "read": False}, {"$set": {"read": True}})
    return {"ok": True}


@api_router.post("/notifications/check-reminders")
async def check_reminders_now(user: User = Depends(get_current_user)):
    user_doc = await db.users.find_one({"user_id": user.user_id}, {"_id": 0})
    r = await _run_reminders_for_user(user_doc)
    return r


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# APScheduler: daily reminder check at 06:00 UTC (09:00 Turkey time)
scheduler = AsyncIOScheduler(timezone="UTC")


@app.on_event("startup")
async def start_scheduler():
    scheduler.add_job(_run_reminders_all_users, CronTrigger(hour=6, minute=0), id="daily_reminders", replace_existing=True)
    scheduler.start()
    logger.info("Reminder scheduler started (daily at 06:00 UTC / 09:00 TR).")


@app.on_event("shutdown")
async def shutdown_db_client():
    try:
        scheduler.shutdown(wait=False)
    except Exception:
        pass
    client.close()
