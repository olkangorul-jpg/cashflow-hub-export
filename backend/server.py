from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import io
import csv
import logging
import uuid
import requests
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal
from datetime import datetime, timezone, timedelta

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

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


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
