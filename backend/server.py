from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, UploadFile, File
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

# Twilio WhatsApp setup
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "")
TWILIO_WHATSAPP_SANDBOX_FROM = os.environ.get("TWILIO_WHATSAPP_SANDBOX_FROM", "")
TWILIO_WHATSAPP_TEMPLATE_SID = os.environ.get("TWILIO_WHATSAPP_TEMPLATE_SID", "")
TWILIO_WHATSAPP_WELCOME_TEMPLATE_SID = os.environ.get("TWILIO_WHATSAPP_WELCOME_TEMPLATE_SID", "")
_twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    from twilio.rest import Client as _TwilioClient
    _twilio_client = _TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

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
    # Computed at auth time (not stored):
    data_owner_id: str = ""  # workspace owner (self OR shared workspace owner)
    workspace_id: str = ""
    workspace_name: str = ""
    role: Literal["owner", "editor", "viewer"] = "owner"


class Workspace(BaseModel):
    model_config = ConfigDict(extra="ignore")
    workspace_id: str
    owner_user_id: str
    name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WorkspaceMember(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    workspace_id: str
    user_id: Optional[str] = None
    email: str
    name: Optional[str] = None
    role: Literal["owner", "editor", "viewer"]
    status: Literal["pending", "active"]
    invited_at: datetime


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
    vat_rate: float = 20.0
    date: str
    bank_account_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExpenseCreate(BaseModel):
    category: str
    description: str
    amount: float
    vat_rate: float = 20.0
    date: str
    bank_account_id: Optional[str] = None


class Income(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    source: str
    description: str
    amount: float
    vat_rate: float = 20.0
    date: str
    bank_account_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class IncomeCreate(BaseModel):
    source: str
    description: str
    amount: float
    vat_rate: float = 20.0
    date: str
    bank_account_id: Optional[str] = None


# ---------------- Auth Helpers ----------------
async def _ensure_personal_workspace(user_id: str, name: str) -> str:
    ws = await db.workspaces.find_one({"owner_user_id": user_id}, {"_id": 0})
    if ws:
        return ws["workspace_id"]
    wid = f"ws_{uuid.uuid4().hex[:12]}"
    await db.workspaces.insert_one({
        "workspace_id": wid,
        "owner_user_id": user_id,
        "name": name or "Kişisel Alan",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return wid


async def _accept_pending_invites(user_id: str, email: str, name: str):
    pending = await db.workspace_members.find(
        {"email": email.lower(), "status": "pending"}, {"_id": 0}
    ).to_list(100)
    for m in pending:
        await db.workspace_members.update_one(
            {"id": m["id"]},
            {"$set": {"user_id": user_id, "name": name, "status": "active", "accepted_at": datetime.now(timezone.utc).isoformat()}},
        )


async def _resolve_workspace_context(user_doc: dict):
    """Return (data_owner_id, workspace_id, workspace_name, role) based on active_workspace_id."""
    uid = user_doc["user_id"]
    active_ws_id = user_doc.get("active_workspace_id")

    if active_ws_id:
        ws = await db.workspaces.find_one({"workspace_id": active_ws_id}, {"_id": 0})
        if ws:
            if ws["owner_user_id"] == uid:
                return uid, ws["workspace_id"], ws["name"], "owner"
            # shared workspace — verify membership
            member = await db.workspace_members.find_one(
                {"workspace_id": active_ws_id, "user_id": uid, "status": "active"}, {"_id": 0}
            )
            if member:
                return ws["owner_user_id"], ws["workspace_id"], ws["name"], member["role"]
    # fallback: personal workspace
    personal_ws_id = await _ensure_personal_workspace(uid, user_doc.get("name") + " - Kişisel" if user_doc.get("name") else "Kişisel Alan")
    ws = await db.workspaces.find_one({"workspace_id": personal_ws_id}, {"_id": 0})
    return uid, personal_ws_id, ws["name"] if ws else "Kişisel Alan", "owner"


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

    data_owner_id, workspace_id, workspace_name, role = await _resolve_workspace_context(user_doc)
    return User(
        user_id=user_doc["user_id"],
        email=user_doc.get("email", ""),
        name=user_doc.get("name", ""),
        picture=user_doc.get("picture"),
        data_owner_id=data_owner_id,
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        role=role,
    )


def require_write(user: User):
    if user.role == "viewer":
        raise HTTPException(status_code=403, detail="Bu workspace'de salt okur yetkiniz var")


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

    # Ensure personal workspace and auto-accept any pending invites
    await _ensure_personal_workspace(user_id, f"{name} - Kişisel" if name else "Kişisel Alan")
    await _accept_pending_invites(user_id, email, name)

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
    return {
        "user_id": user.user_id,
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "workspace_id": user.workspace_id,
        "workspace_name": user.workspace_name,
        "role": user.role,
    }


@api_router.post("/auth/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get("session_token")
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    response.delete_cookie("session_token", path="/")
    return {"ok": True}


# ---------------- Workspaces / Team ----------------
class InviteRequest(BaseModel):
    email: str
    role: Literal["editor", "viewer"] = "editor"


class SwitchWorkspaceRequest(BaseModel):
    workspace_id: str


class RenameWorkspaceRequest(BaseModel):
    name: str


@api_router.get("/workspaces")
async def list_workspaces(user: User = Depends(get_current_user)):
    # Own workspaces
    owned = await db.workspaces.find({"owner_user_id": user.user_id}, {"_id": 0}).to_list(100)
    # Workspaces where user is a member (accepted)
    memberships = await db.workspace_members.find(
        {"user_id": user.user_id, "status": "active"}, {"_id": 0}
    ).to_list(100)
    shared_ids = [m["workspace_id"] for m in memberships]
    shared = []
    if shared_ids:
        shared = await db.workspaces.find({"workspace_id": {"$in": shared_ids}}, {"_id": 0}).to_list(100)

    def _fmt(ws, role):
        return {
            "workspace_id": ws["workspace_id"],
            "name": ws["name"],
            "owner_user_id": ws["owner_user_id"],
            "role": role,
            "is_active": ws["workspace_id"] == user.workspace_id,
        }

    items = [_fmt(w, "owner") for w in owned]
    m_by_ws = {m["workspace_id"]: m for m in memberships}
    for w in shared:
        items.append(_fmt(w, m_by_ws.get(w["workspace_id"], {}).get("role", "viewer")))
    return items


@api_router.post("/workspaces/switch")
async def switch_workspace(payload: SwitchWorkspaceRequest, user: User = Depends(get_current_user)):
    wid = payload.workspace_id
    ws = await db.workspaces.find_one({"workspace_id": wid}, {"_id": 0})
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace bulunamadı")
    if ws["owner_user_id"] != user.user_id:
        member = await db.workspace_members.find_one(
            {"workspace_id": wid, "user_id": user.user_id, "status": "active"}, {"_id": 0}
        )
        if not member:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
    await db.users.update_one({"user_id": user.user_id}, {"$set": {"active_workspace_id": wid}})
    return {"ok": True, "workspace_id": wid}


@api_router.put("/workspaces/{workspace_id}/rename")
async def rename_workspace(workspace_id: str, payload: RenameWorkspaceRequest, user: User = Depends(get_current_user)):
    ws = await db.workspaces.find_one({"workspace_id": workspace_id, "owner_user_id": user.user_id}, {"_id": 0})
    if not ws:
        raise HTTPException(status_code=403, detail="Sadece sahibi yeniden adlandırabilir")
    name = (payload.name or "").strip()[:60]
    if not name:
        raise HTTPException(status_code=400, detail="İsim boş olamaz")
    await db.workspaces.update_one({"workspace_id": workspace_id}, {"$set": {"name": name}})
    return {"ok": True, "name": name}


@api_router.get("/workspaces/{workspace_id}/members")
async def list_members(workspace_id: str, user: User = Depends(get_current_user)):
    ws = await db.workspaces.find_one({"workspace_id": workspace_id}, {"_id": 0})
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace bulunamadı")
    # Only owner or an active member can view
    if ws["owner_user_id"] != user.user_id:
        m = await db.workspace_members.find_one({"workspace_id": workspace_id, "user_id": user.user_id, "status": "active"}, {"_id": 0})
        if not m:
            raise HTTPException(status_code=403, detail="Yetkiniz yok")
    owner_doc = await db.users.find_one({"user_id": ws["owner_user_id"]}, {"_id": 0})
    members = await db.workspace_members.find({"workspace_id": workspace_id}, {"_id": 0}).to_list(200)
    result = [{
        "id": "owner",
        "email": owner_doc.get("email") if owner_doc else "",
        "name": owner_doc.get("name") if owner_doc else "",
        "role": "owner",
        "status": "active",
    }]
    for m in members:
        result.append({
            "id": m["id"], "email": m["email"], "name": m.get("name"),
            "role": m["role"], "status": m["status"],
        })
    return result


@api_router.post("/workspaces/{workspace_id}/invite")
async def invite_member(workspace_id: str, payload: InviteRequest, user: User = Depends(get_current_user)):
    ws = await db.workspaces.find_one({"workspace_id": workspace_id, "owner_user_id": user.user_id}, {"_id": 0})
    if not ws:
        raise HTTPException(status_code=403, detail="Sadece sahibi davet gönderebilir")
    email = (payload.email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Geçersiz email")
    if email == user.email.lower():
        raise HTTPException(status_code=400, detail="Kendinizi davet edemezsiniz")

    # If already invited to this workspace, update role
    existing = await db.workspace_members.find_one({"workspace_id": workspace_id, "email": email}, {"_id": 0})
    if existing:
        await db.workspace_members.update_one(
            {"id": existing["id"]}, {"$set": {"role": payload.role}}
        )
        member_id = existing["id"]
        status = existing["status"]
    else:
        member_id = f"mem_{uuid.uuid4().hex[:12]}"
        # Check if invitee already has an account
        existing_user = await db.users.find_one({"email": email}, {"_id": 0})
        status = "active" if existing_user else "pending"
        await db.workspace_members.insert_one({
            "id": member_id,
            "workspace_id": workspace_id,
            "user_id": existing_user["user_id"] if existing_user else None,
            "email": email,
            "name": existing_user.get("name") if existing_user else None,
            "role": payload.role,
            "status": status,
            "invited_at": datetime.now(timezone.utc).isoformat(),
        })

    # Send invite email (best-effort)
    invite_url = os.environ.get("APP_URL", "").rstrip("/")
    login_link = f"{invite_url}/login" if invite_url else "/login"
    html = f"""
    <html><body style="margin:0;background:#F8F9FA;padding:24px;font-family:Arial,sans-serif;">
      <table role="presentation" width="100%" style="max-width:600px;margin:0 auto;background:#fff;border:1px solid #E2E8F0;border-radius:6px;">
        <tr><td style="padding:24px;border-bottom:1px solid #E2E8F0;">
          <h1 style="margin:0;font-size:20px;color:#0F172A;">Nakit Akış'a Davet Edildiniz</h1>
        </td></tr>
        <tr><td style="padding:24px;color:#334155;font-size:14px;line-height:1.6;">
          <p><strong>{user.name}</strong> sizi <strong>{ws['name']}</strong> workspace'ine <strong>{payload.role}</strong> yetkisi ile davet etti.</p>
          <p>Aşağıdaki bağlantı ile Google hesabınız ({email}) üzerinden giriş yaptığınızda otomatik olarak workspace'e katılırsınız.</p>
          <p style="margin:24px 0;">
            <a href="{login_link}" style="background:#0F172A;color:#fff;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:600;">Giriş Yap ve Katıl</a>
          </p>
        </td></tr>
      </table>
    </body></html>
    """
    await _send_email(email, f"{user.name} sizi Nakit Akış'a davet etti", html)
    return {"ok": True, "member_id": member_id, "status": status}


@api_router.delete("/workspaces/{workspace_id}/members/{member_id}")
async def remove_member(workspace_id: str, member_id: str, user: User = Depends(get_current_user)):
    ws = await db.workspaces.find_one({"workspace_id": workspace_id, "owner_user_id": user.user_id}, {"_id": 0})
    if not ws:
        raise HTTPException(status_code=403, detail="Sadece sahibi üye çıkarabilir")
    if member_id == "owner":
        raise HTTPException(status_code=400, detail="Sahibi kaldırılamaz")
    await db.workspace_members.delete_one({"id": member_id, "workspace_id": workspace_id})
    return {"ok": True}


# ---------------- Bank Accounts ----------------
@api_router.get("/bank-accounts", response_model=List[BankAccount])
async def list_bank_accounts(user: User = Depends(get_current_user)):
    docs = await db.bank_accounts.find({"user_id": user.data_owner_id}, {"_id": 0}).to_list(1000)
    return [BankAccount(**d) for d in docs]


@api_router.post("/bank-accounts", response_model=BankAccount)
async def create_bank_account(payload: BankAccountCreate, user: User = Depends(get_current_user)):
    obj = BankAccount(user_id=user.data_owner_id, **payload.model_dump())
    d = obj.model_dump()
    d["created_at"] = d["created_at"].isoformat()
    await db.bank_accounts.insert_one(d)
    return obj


@api_router.put("/bank-accounts/{account_id}", response_model=BankAccount)
async def update_bank_account(account_id: str, payload: BankAccountCreate, user: User = Depends(get_current_user)):
    res = await db.bank_accounts.update_one(
        {"id": account_id, "user_id": user.data_owner_id},
        {"$set": payload.model_dump()},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    doc = await db.bank_accounts.find_one({"id": account_id}, {"_id": 0})
    return BankAccount(**doc)


@api_router.delete("/bank-accounts/{account_id}")
async def delete_bank_account(account_id: str, user: User = Depends(get_current_user)):
    await db.bank_accounts.delete_one({"id": account_id, "user_id": user.data_owner_id})
    return {"ok": True}


# ---------------- Checks ----------------
@api_router.get("/checks", response_model=List[Check])
async def list_checks(
    user: User = Depends(get_current_user),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    q = {"user_id": user.data_owner_id}
    if start_date or end_date:
        q["due_date"] = {}
        if start_date:
            q["due_date"]["$gte"] = start_date
        if end_date:
            q["due_date"]["$lte"] = end_date
    docs = await db.checks.find(q, {"_id": 0}).sort("due_date", 1).to_list(2000)
    return [Check(**d) for d in docs]


@api_router.post("/checks", response_model=Check)
async def create_check(payload: CheckCreate, user: User = Depends(get_current_user)):
    obj = Check(user_id=user.data_owner_id, **payload.model_dump())
    d = obj.model_dump()
    d["created_at"] = d["created_at"].isoformat()
    await db.checks.insert_one(d)
    return obj


@api_router.put("/checks/{check_id}", response_model=Check)
async def update_check(check_id: str, payload: CheckCreate, user: User = Depends(get_current_user)):
    res = await db.checks.update_one(
        {"id": check_id, "user_id": user.data_owner_id},
        {"$set": payload.model_dump()},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    doc = await db.checks.find_one({"id": check_id}, {"_id": 0})
    return Check(**doc)


@api_router.delete("/checks/{check_id}")
async def delete_check(check_id: str, user: User = Depends(get_current_user)):
    await db.checks.delete_one({"id": check_id, "user_id": user.data_owner_id})
    return {"ok": True}


# ---------------- Promissory Notes ----------------
@api_router.get("/promissory-notes", response_model=List[PromissoryNote])
async def list_notes(
    user: User = Depends(get_current_user),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    q = {"user_id": user.data_owner_id}
    if start_date or end_date:
        q["due_date"] = {}
        if start_date:
            q["due_date"]["$gte"] = start_date
        if end_date:
            q["due_date"]["$lte"] = end_date
    docs = await db.promissory_notes.find(q, {"_id": 0}).sort("due_date", 1).to_list(2000)
    return [PromissoryNote(**d) for d in docs]


@api_router.post("/promissory-notes", response_model=PromissoryNote)
async def create_note(payload: PromissoryNoteCreate, user: User = Depends(get_current_user)):
    obj = PromissoryNote(user_id=user.data_owner_id, **payload.model_dump())
    d = obj.model_dump()
    d["created_at"] = d["created_at"].isoformat()
    await db.promissory_notes.insert_one(d)
    return obj


@api_router.put("/promissory-notes/{note_id}", response_model=PromissoryNote)
async def update_note(note_id: str, payload: PromissoryNoteCreate, user: User = Depends(get_current_user)):
    res = await db.promissory_notes.update_one(
        {"id": note_id, "user_id": user.data_owner_id},
        {"$set": payload.model_dump()},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    doc = await db.promissory_notes.find_one({"id": note_id}, {"_id": 0})
    return PromissoryNote(**doc)


@api_router.delete("/promissory-notes/{note_id}")
async def delete_note(note_id: str, user: User = Depends(get_current_user)):
    await db.promissory_notes.delete_one({"id": note_id, "user_id": user.data_owner_id})
    return {"ok": True}


# ---------------- Expenses ----------------
@api_router.get("/expenses", response_model=List[Expense])
async def list_expenses(
    user: User = Depends(get_current_user),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    q = {"user_id": user.data_owner_id}
    if start_date or end_date:
        q["date"] = {}
        if start_date:
            q["date"]["$gte"] = start_date
        if end_date:
            q["date"]["$lte"] = end_date
    docs = await db.expenses.find(q, {"_id": 0}).sort("date", -1).to_list(2000)
    return [Expense(**d) for d in docs]


@api_router.post("/expenses", response_model=Expense)
async def create_expense(payload: ExpenseCreate, user: User = Depends(get_current_user)):
    obj = Expense(user_id=user.data_owner_id, **payload.model_dump())
    d = obj.model_dump()
    d["created_at"] = d["created_at"].isoformat()
    await db.expenses.insert_one(d)
    return obj


@api_router.put("/expenses/{expense_id}", response_model=Expense)
async def update_expense(expense_id: str, payload: ExpenseCreate, user: User = Depends(get_current_user)):
    res = await db.expenses.update_one(
        {"id": expense_id, "user_id": user.data_owner_id},
        {"$set": payload.model_dump()},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    doc = await db.expenses.find_one({"id": expense_id}, {"_id": 0})
    return Expense(**doc)


@api_router.delete("/expenses/{expense_id}")
async def delete_expense(expense_id: str, user: User = Depends(get_current_user)):
    await db.expenses.delete_one({"id": expense_id, "user_id": user.data_owner_id})
    return {"ok": True}


# ---------------- Incomes ----------------
@api_router.get("/incomes", response_model=List[Income])
async def list_incomes(
    user: User = Depends(get_current_user),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    q = {"user_id": user.data_owner_id}
    if start_date or end_date:
        q["date"] = {}
        if start_date:
            q["date"]["$gte"] = start_date
        if end_date:
            q["date"]["$lte"] = end_date
    docs = await db.incomes.find(q, {"_id": 0}).sort("date", -1).to_list(2000)
    return [Income(**d) for d in docs]


@api_router.post("/incomes", response_model=Income)
async def create_income(payload: IncomeCreate, user: User = Depends(get_current_user)):
    obj = Income(user_id=user.data_owner_id, **payload.model_dump())
    d = obj.model_dump()
    d["created_at"] = d["created_at"].isoformat()
    await db.incomes.insert_one(d)
    return obj


@api_router.put("/incomes/{income_id}", response_model=Income)
async def update_income(income_id: str, payload: IncomeCreate, user: User = Depends(get_current_user)):
    res = await db.incomes.update_one(
        {"id": income_id, "user_id": user.data_owner_id},
        {"$set": payload.model_dump()},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    doc = await db.incomes.find_one({"id": income_id}, {"_id": 0})
    return Income(**doc)


@api_router.delete("/incomes/{income_id}")
async def delete_income(income_id: str, user: User = Depends(get_current_user)):
    await db.incomes.delete_one({"id": income_id, "user_id": user.data_owner_id})
    return {"ok": True}


# ---------------- Dashboard / Analytics ----------------
@api_router.get("/dashboard/summary")
async def dashboard_summary(user: User = Depends(get_current_user)):
    uid = user.data_owner_id
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
    docs = await db.checks.find({"user_id": user.data_owner_id}, {"_id": 0}).to_list(5000)
    return _stream_csv(docs, ["type", "party", "amount", "due_date", "bank_name", "check_number", "status", "notes"], "cekler.csv")


@api_router.get("/export/promissory-notes")
async def export_notes(user: User = Depends(get_current_user)):
    docs = await db.promissory_notes.find({"user_id": user.data_owner_id}, {"_id": 0}).to_list(5000)
    return _stream_csv(docs, ["type", "party", "amount", "due_date", "status", "notes"], "senetler.csv")


@api_router.get("/export/expenses")
async def export_expenses(user: User = Depends(get_current_user)):
    docs = await db.expenses.find({"user_id": user.data_owner_id}, {"_id": 0}).to_list(5000)
    return _stream_csv(docs, ["category", "description", "amount", "date", "bank_account_id"], "giderler.csv")


@api_router.get("/export/incomes")
async def export_incomes(user: User = Depends(get_current_user)):
    docs = await db.incomes.find({"user_id": user.data_owner_id}, {"_id": 0}).to_list(5000)
    return _stream_csv(docs, ["source", "description", "amount", "date", "bank_account_id"], "gelirler.csv")


# ---------------- PDF Report ----------------
_PDF_FONT_REGISTERED = False


def _register_pdf_font():
    global _PDF_FONT_REGISTERED
    if _PDF_FONT_REGISTERED:
        return
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.rl_config import defaultPageSize  # noqa
    import reportlab
    base = Path(reportlab.__file__).parent / "fonts"
    pdfmetrics.registerFont(TTFont("Vera", str(base / "Vera.ttf")))
    pdfmetrics.registerFont(TTFont("Vera-Bold", str(base / "VeraBd.ttf")))
    _PDF_FONT_REGISTERED = True


def _fmt_try(v: float) -> str:
    s = f"{v:,.2f}"
    # Turkish format: 1.234,56
    return s.replace(",", "X").replace(".", ",").replace("X", ".") + " ₺"


@api_router.get("/reports/pdf")
async def report_pdf(
    user: User = Depends(get_current_user),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

    _register_pdf_font()

    # Default: current month
    today = datetime.now(timezone.utc).date()
    if not start_date:
        start_date = today.replace(day=1).isoformat()
    if not end_date:
        end_date = today.isoformat()

    uid = user.data_owner_id

    def _in_range(d):
        return start_date <= d <= end_date

    incomes = [i for i in await db.incomes.find({"user_id": uid}, {"_id": 0}).to_list(5000) if _in_range(i["date"])]
    expenses = [e for e in await db.expenses.find({"user_id": uid}, {"_id": 0}).to_list(5000) if _in_range(e["date"])]
    checks = [c for c in await db.checks.find({"user_id": uid}, {"_id": 0}).to_list(5000) if _in_range(c["due_date"])]
    notes = [n for n in await db.promissory_notes.find({"user_id": uid}, {"_id": 0}).to_list(5000) if _in_range(n["due_date"])]
    accounts = await db.bank_accounts.find({"user_id": uid}, {"_id": 0}).to_list(5000)

    total_income = sum(i["amount"] for i in incomes)
    total_expense = sum(e["amount"] for e in expenses)
    total_balance = sum(a.get("balance", 0.0) for a in accounts)
    net = total_income - total_expense

    # Build PDF
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm, leftMargin=1.5 * cm, rightMargin=1.5 * cm)
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontName="Vera-Bold", fontSize=20, textColor=colors.HexColor("#0F172A"), spaceAfter=6)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName="Vera-Bold", fontSize=13, textColor=colors.HexColor("#0F172A"), spaceBefore=12, spaceAfter=8)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontName="Vera", fontSize=10, textColor=colors.HexColor("#334155"))
    meta = ParagraphStyle("meta", parent=styles["BodyText"], fontName="Vera", fontSize=9, textColor=colors.HexColor("#64748B"))

    story = []
    story.append(Paragraph("Nakit Akış Raporu", h1))
    story.append(Paragraph(
        f"Dönem: <b>{start_date}</b> — <b>{end_date}</b> · Oluşturuldu: {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M UTC')}",
        meta,
    ))
    story.append(Paragraph(f"Kullanıcı: {user.name} ({user.email})", meta))
    story.append(Spacer(1, 0.5 * cm))

    # KPI Table
    kpi_data = [
        ["Toplam Bakiye (Tüm Hesaplar)", _fmt_try(total_balance)],
        ["Dönem Geliri", _fmt_try(total_income)],
        ["Dönem Gideri", _fmt_try(total_expense)],
        ["Net", _fmt_try(net)],
    ]
    kpi_table = Table(kpi_data, colWidths=[10 * cm, 6 * cm])
    kpi_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Vera"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F8FAFC")),
        ("FONTNAME", (0, 0), (0, -1), "Vera-Bold"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("TEXTCOLOR", (1, 3), (1, 3), colors.HexColor("#166534") if net >= 0 else colors.HexColor("#991B1B")),
        ("FONTNAME", (1, 3), (1, 3), "Vera-Bold"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(kpi_table)

    # Category breakdown
    cat = {}
    for e in expenses:
        cat[e["category"]] = cat.get(e["category"], 0) + e["amount"]
    if cat:
        story.append(Paragraph("Gider Kategorileri", h2))
        rows = [["Kategori", "Tutar", "Oran"]]
        for k, v in sorted(cat.items(), key=lambda x: -x[1]):
            pct = (v / total_expense * 100) if total_expense else 0
            rows.append([k, _fmt_try(v), f"%{pct:.1f}"])
        tbl = Table(rows, colWidths=[8 * cm, 5 * cm, 3 * cm])
        tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Vera"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Vera-Bold"),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(tbl)

    # Upcoming pending checks + notes
    pending = [{"kind": "Çek", **c} for c in checks if c.get("status") == "pending"] + \
              [{"kind": "Senet", **n} for n in notes if n.get("status") == "pending"]
    pending.sort(key=lambda x: x["due_date"])
    if pending:
        story.append(Paragraph("Dönemdeki Bekleyen Çek & Senetler", h2))
        rows = [["Tür", "Yön", "Karşı Taraf", "Vade", "Tutar"]]
        for p in pending:
            direction = "Alacak" if p["type"] == "received" else "Borç"
            rows.append([p["kind"], direction, p["party"][:30], p["due_date"], _fmt_try(p["amount"])])
        tbl = Table(rows, colWidths=[2 * cm, 2 * cm, 6.5 * cm, 2.5 * cm, 3 * cm])
        tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Vera"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Vera-Bold"),
            ("ALIGN", (4, 0), (4, -1), "RIGHT"),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(tbl)

    # Income table
    if incomes:
        story.append(Paragraph("Gelirler", h2))
        rows = [["Kaynak", "Açıklama", "Tarih", "Tutar"]]
        for i in incomes:
            rows.append([i["source"][:20], (i.get("description") or "-")[:35], i["date"], _fmt_try(i["amount"])])
        tbl = Table(rows, colWidths=[4 * cm, 7 * cm, 2.5 * cm, 3 * cm])
        tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Vera"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#166534")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Vera-Bold"),
            ("ALIGN", (3, 0), (3, -1), "RIGHT"),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(tbl)

    # Expense table
    if expenses:
        story.append(Paragraph("Giderler", h2))
        rows = [["Kategori", "Açıklama", "Tarih", "Tutar"]]
        for e in expenses:
            rows.append([e["category"][:20], (e.get("description") or "-")[:35], e["date"], _fmt_try(e["amount"])])
        tbl = Table(rows, colWidths=[4 * cm, 7 * cm, 2.5 * cm, 3 * cm])
        tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Vera"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#991B1B")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Vera-Bold"),
            ("ALIGN", (3, 0), (3, -1), "RIGHT"),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(tbl)

    if not (incomes or expenses or pending):
        story.append(Spacer(1, 0.5 * cm))
        story.append(Paragraph("Seçilen dönemde kayıt bulunmuyor.", body))

    doc.build(story)
    buf.seek(0)
    filename = f"nakit-akis-raporu-{start_date}-{end_date}.pdf"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api_router.get("/")
async def root():
    return {"message": "Nakit Akış API"}


# ---------------- Tax / KDV Report ----------------
def _compute_vat_breakdown(items: List[dict]) -> dict:
    """Split items by vat_rate. Amounts are gross (KDV dahil)."""
    by_rate = {}
    for it in items:
        rate = float(it.get("vat_rate") or 0)
        gross = float(it.get("amount") or 0)
        vat = gross * rate / (100 + rate) if rate > 0 else 0.0
        net = gross - vat
        b = by_rate.setdefault(rate, {"rate": rate, "gross": 0.0, "net": 0.0, "vat": 0.0, "count": 0})
        b["gross"] += gross
        b["net"] += net
        b["vat"] += vat
        b["count"] += 1
    return by_rate


@api_router.get("/reports/tax")
async def tax_report(
    user: User = Depends(get_current_user),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    period: Optional[str] = None,  # YYYY-MM (monthly) or YYYY-Q1..Q4 (quarterly)
):
    today = datetime.now(timezone.utc).date()
    # Resolve period shortcut
    if period:
        try:
            if "-Q" in period:
                y, q = period.split("-Q")
                y, q = int(y), int(q)
                start_m = (q - 1) * 3 + 1
                start_date = date(y, start_m, 1).isoformat()
                end_m = start_m + 2
                # last day of end_m
                if end_m == 12:
                    end_date = date(y, 12, 31).isoformat()
                else:
                    end_date = (date(y, end_m + 1, 1) - timedelta(days=1)).isoformat()
            else:
                y, m = map(int, period.split("-"))
                start_date = date(y, m, 1).isoformat()
                if m == 12:
                    end_date = date(y, 12, 31).isoformat()
                else:
                    end_date = (date(y, m + 1, 1) - timedelta(days=1)).isoformat()
        except Exception:
            raise HTTPException(status_code=400, detail="Geçersiz dönem")
    if not start_date:
        start_date = today.replace(day=1).isoformat()
    if not end_date:
        end_date = today.isoformat()

    uid = user.data_owner_id
    incomes = [i for i in await db.incomes.find({"user_id": uid}, {"_id": 0}).to_list(5000)
               if start_date <= i["date"] <= end_date]
    expenses = [e for e in await db.expenses.find({"user_id": uid}, {"_id": 0}).to_list(5000)
                if start_date <= e["date"] <= end_date]

    inc_break = _compute_vat_breakdown(incomes)
    exp_break = _compute_vat_breakdown(expenses)

    inc_total = {"gross": sum(b["gross"] for b in inc_break.values()),
                 "net": sum(b["net"] for b in inc_break.values()),
                 "vat": sum(b["vat"] for b in inc_break.values())}
    exp_total = {"gross": sum(b["gross"] for b in exp_break.values()),
                 "net": sum(b["net"] for b in exp_break.values()),
                 "vat": sum(b["vat"] for b in exp_break.values())}

    # Hesaplanan KDV (income VAT), İndirilecek KDV (expense VAT), Ödenecek KDV (positive = pay, negative = refund)
    payable_vat = inc_total["vat"] - exp_total["vat"]

    return {
        "start_date": start_date,
        "end_date": end_date,
        "period": period,
        "income": {
            "total_gross": round(inc_total["gross"], 2),
            "total_net": round(inc_total["net"], 2),
            "total_vat": round(inc_total["vat"], 2),
            "count": len(incomes),
            "breakdown": [{"rate": r, "gross": round(b["gross"], 2), "net": round(b["net"], 2),
                           "vat": round(b["vat"], 2), "count": b["count"]}
                          for r, b in sorted(inc_break.items())],
        },
        "expense": {
            "total_gross": round(exp_total["gross"], 2),
            "total_net": round(exp_total["net"], 2),
            "total_vat": round(exp_total["vat"], 2),
            "count": len(expenses),
            "breakdown": [{"rate": r, "gross": round(b["gross"], 2), "net": round(b["net"], 2),
                           "vat": round(b["vat"], 2), "count": b["count"]}
                          for r, b in sorted(exp_break.items())],
        },
        "payable_vat": round(payable_vat, 2),
        "vat_status": "pay" if payable_vat > 0 else ("refund" if payable_vat < 0 else "even"),
    }


@api_router.get("/reports/tax/pdf")
async def tax_report_pdf(
    user: User = Depends(get_current_user),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    period: Optional[str] = None,
):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    _register_pdf_font()
    data = await tax_report(user=user, start_date=start_date, end_date=end_date, period=period)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm, leftMargin=1.5 * cm, rightMargin=1.5 * cm)
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontName="Vera-Bold", fontSize=20, textColor=colors.HexColor("#0F172A"), spaceAfter=6)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName="Vera-Bold", fontSize=13, textColor=colors.HexColor("#0F172A"), spaceBefore=14, spaceAfter=6)
    meta = ParagraphStyle("meta", parent=styles["BodyText"], fontName="Vera", fontSize=9, textColor=colors.HexColor("#64748B"))

    story = []
    story.append(Paragraph("KDV Beyan Özeti", h1))
    story.append(Paragraph(
        f"Dönem: <b>{data['start_date']}</b> — <b>{data['end_date']}</b> · Oluşturuldu: {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M UTC')}",
        meta,
    ))
    story.append(Paragraph(f"Kullanıcı: {user.name} ({user.email})", meta))
    story.append(Spacer(1, 0.5 * cm))

    def _t_style():
        return TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Vera"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Vera-Bold"),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ])

    # Summary row
    summary = [["", "Matrah (KDV Hariç)", "KDV", "Brüt (KDV Dahil)", "Adet"]]
    summary.append(["Gelir (Hesaplanan KDV)", _fmt_try(data["income"]["total_net"]),
                    _fmt_try(data["income"]["total_vat"]),
                    _fmt_try(data["income"]["total_gross"]),
                    str(data["income"]["count"])])
    summary.append(["Gider (İndirilecek KDV)", _fmt_try(data["expense"]["total_net"]),
                    _fmt_try(data["expense"]["total_vat"]),
                    _fmt_try(data["expense"]["total_gross"]),
                    str(data["expense"]["count"])])
    tbl = Table(summary, colWidths=[6 * cm, 3.5 * cm, 3.5 * cm, 3.5 * cm, 1.5 * cm])
    tbl.setStyle(_t_style())
    story.append(tbl)

    story.append(Spacer(1, 0.4 * cm))
    # VAT Payable
    status_text = "Ödenecek KDV" if data["vat_status"] == "pay" else ("İade Alınacak KDV" if data["vat_status"] == "refund" else "Denk")
    color = "#991B1B" if data["vat_status"] == "pay" else ("#166534" if data["vat_status"] == "refund" else "#0F172A")
    pv = data["payable_vat"]
    story.append(Table(
        [[Paragraph(f"<b>{status_text}</b>", ParagraphStyle('x', fontName='Vera-Bold', fontSize=13, textColor=colors.HexColor('#0F172A'))),
          Paragraph(f'<font color="{color}"><b>{_fmt_try(abs(pv))}</b></font>',
                    ParagraphStyle('y', fontName='Vera-Bold', fontSize=13, alignment=2))]],
        colWidths=[10 * cm, 8 * cm],
        style=TableStyle([
            ("BOX", (0, 0), (-1, -1), 1.0, colors.HexColor("#0F172A")),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
            ("TOPPADDING", (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ])
    ))

    # Income breakdown
    if data["income"]["breakdown"]:
        story.append(Paragraph("Gelir KDV Kırılımı", h2))
        rows = [["KDV Oranı", "Matrah", "KDV", "Brüt", "Adet"]]
        for b in data["income"]["breakdown"]:
            rows.append([f"%{b['rate']:g}", _fmt_try(b["net"]), _fmt_try(b["vat"]),
                         _fmt_try(b["gross"]), str(b["count"])])
        tbl = Table(rows, colWidths=[3 * cm, 4 * cm, 4 * cm, 4 * cm, 2 * cm])
        tbl.setStyle(_t_style())
        story.append(tbl)

    # Expense breakdown
    if data["expense"]["breakdown"]:
        story.append(Paragraph("Gider KDV Kırılımı", h2))
        rows = [["KDV Oranı", "Matrah", "KDV", "Brüt", "Adet"]]
        for b in data["expense"]["breakdown"]:
            rows.append([f"%{b['rate']:g}", _fmt_try(b["net"]), _fmt_try(b["vat"]),
                         _fmt_try(b["gross"]), str(b["count"])])
        tbl = Table(rows, colWidths=[3 * cm, 4 * cm, 4 * cm, 4 * cm, 2 * cm])
        tbl.setStyle(_t_style())
        story.append(tbl)

    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(
        "<i>Not: Tutarlar KDV dahil brüt varsayılmıştır. Bu rapor bilgi amaçlıdır ve resmi beyan yerine geçmez.</i>",
        meta,
    ))

    doc.build(story)
    buf.seek(0)
    filename = f"kdv-raporu-{data['start_date']}-{data['end_date']}.pdf"
    return StreamingResponse(iter([buf.getvalue()]), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@api_router.get("/reports/tax/xlsx")
async def tax_report_xlsx(
    user: User = Depends(get_current_user),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    period: Optional[str] = None,
):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    data = await tax_report(user=user, start_date=start_date, end_date=end_date, period=period)
    wb = Workbook()
    ws = wb.active
    ws.title = "KDV Özeti"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="0F172A")
    right = Alignment(horizontal="right")

    ws.append(["KDV Beyan Özeti"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([f"Dönem: {data['start_date']} - {data['end_date']}"])
    ws.append([])

    # Summary
    for row_idx, row in enumerate([
        ["", "Matrah", "KDV", "Brüt", "Adet"],
        ["Gelir", data["income"]["total_net"], data["income"]["total_vat"], data["income"]["total_gross"], data["income"]["count"]],
        ["Gider", data["expense"]["total_net"], data["expense"]["total_vat"], data["expense"]["total_gross"], data["expense"]["count"]],
    ]):
        ws.append(row)
        if row_idx == 0:
            for c in ws[ws.max_row]:
                c.font = header_font
                c.fill = header_fill
                c.alignment = right

    ws.append([])
    ws.append(["Ödenecek/İade KDV", data["payable_vat"]])
    ws[f"A{ws.max_row}"].font = Font(bold=True)

    ws.append([])
    ws.append(["Gelir KDV Kırılımı"])
    ws[f"A{ws.max_row}"].font = Font(bold=True)
    ws.append(["KDV Oranı", "Matrah", "KDV", "Brüt", "Adet"])
    for c in ws[ws.max_row]:
        c.font = header_font
        c.fill = header_fill
    for b in data["income"]["breakdown"]:
        ws.append([f"%{b['rate']:g}", b["net"], b["vat"], b["gross"], b["count"]])

    ws.append([])
    ws.append(["Gider KDV Kırılımı"])
    ws[f"A{ws.max_row}"].font = Font(bold=True)
    ws.append(["KDV Oranı", "Matrah", "KDV", "Brüt", "Adet"])
    for c in ws[ws.max_row]:
        c.font = header_font
        c.fill = header_fill
    for b in data["expense"]["breakdown"]:
        ws.append([f"%{b['rate']:g}", b["net"], b["vat"], b["gross"], b["count"]])

    for i, w in enumerate([22, 18, 18, 18, 12], 1):
        ws.column_dimensions[chr(64 + i)].width = w

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"kdv-raporu-{data['start_date']}-{data['end_date']}.xlsx"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------- Backups ----------------
BACKUP_COLLECTIONS = ["bank_accounts", "checks", "promissory_notes", "expenses", "incomes"]


async def _create_backup(user_id: str, workspace_id: str, kind: str = "manual") -> dict:
    payload = {}
    for c in BACKUP_COLLECTIONS:
        docs = await db[c].find({"user_id": user_id}, {"_id": 0}).to_list(20000)
        payload[c] = docs
    total_records = sum(len(v) for v in payload.values())
    backup_id = f"bak_{uuid.uuid4().hex[:12]}"
    doc = {
        "id": backup_id,
        "workspace_id": workspace_id,
        "user_id": user_id,
        "kind": kind,  # manual / auto
        "collections": list(BACKUP_COLLECTIONS),
        "total_records": total_records,
        "payload": payload,
        "size_bytes": len(str(payload)),  # approximate
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.backups.insert_one(doc)

    # Retention: keep last 10 per workspace
    old = await db.backups.find({"workspace_id": workspace_id}, {"_id": 0, "id": 1, "created_at": 1}).sort("created_at", -1).to_list(200)
    if len(old) > 10:
        to_delete = [o["id"] for o in old[10:]]
        await db.backups.delete_many({"id": {"$in": to_delete}})
    return {
        "id": doc["id"],
        "workspace_id": doc["workspace_id"],
        "kind": doc["kind"],
        "collections": doc["collections"],
        "total_records": doc["total_records"],
        "size_bytes": doc["size_bytes"],
        "created_at": doc["created_at"],
    }


@api_router.post("/backups")
async def create_backup(user: User = Depends(get_current_user)):
    b = await _create_backup(user.data_owner_id, user.workspace_id, "manual")
    return b


@api_router.get("/backups")
async def list_backups(user: User = Depends(get_current_user)):
    docs = await db.backups.find({"workspace_id": user.workspace_id}, {"_id": 0, "payload": 0}).sort("created_at", -1).to_list(50)
    return docs


@api_router.get("/backups/{backup_id}/download")
async def download_backup(backup_id: str, user: User = Depends(get_current_user)):
    doc = await db.backups.find_one({"id": backup_id, "workspace_id": user.workspace_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Yedek bulunamadı")
    import json as _json
    body = _json.dumps({
        "version": 1,
        "workspace_id": user.workspace_id,
        "workspace_name": user.workspace_name,
        "created_at": doc["created_at"],
        "kind": doc["kind"],
        "collections": doc["collections"],
        "total_records": doc["total_records"],
        "payload": doc["payload"],
    }, ensure_ascii=False, indent=2)
    filename = f"nakit-akis-yedek-{doc['created_at'][:10]}-{backup_id}.json"
    return StreamingResponse(
        iter([body.encode("utf-8")]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api_router.delete("/backups/{backup_id}")
async def delete_backup(backup_id: str, user: User = Depends(get_current_user)):
    res = await db.backups.delete_one({"id": backup_id, "workspace_id": user.workspace_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Yedek bulunamadı")
    return {"ok": True}


@api_router.post("/backups/{backup_id}/restore")
async def restore_backup(
    backup_id: str,
    mode: str = "merge",  # merge | replace
    user: User = Depends(get_current_user),
):
    if user.role == "viewer":
        raise HTTPException(status_code=403, detail="Bu workspace'de salt okur yetkiniz var")
    doc = await db.backups.find_one({"id": backup_id, "workspace_id": user.workspace_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Yedek bulunamadı")

    uid = user.data_owner_id
    restored = 0
    if mode == "replace":
        for c in doc["collections"]:
            await db[c].delete_many({"user_id": uid})

    for c in doc["collections"]:
        records = doc["payload"].get(c, [])
        if not records:
            continue
        new_records = []
        for r in records:
            r = {**r}
            r["user_id"] = uid  # ensure ownership matches current workspace
            if mode == "merge":
                r["id"] = str(uuid.uuid4())  # avoid collision
            new_records.append(r)
        if new_records:
            await db[c].insert_many(new_records)
            restored += len(new_records)
    return {"ok": True, "restored": restored, "mode": mode}


@api_router.post("/backups/restore-file")
async def restore_from_file(
    file: UploadFile = File(...),
    mode: str = "merge",
    user: User = Depends(get_current_user),
):
    if user.role == "viewer":
        raise HTTPException(status_code=403, detail="Bu workspace'de salt okur yetkiniz var")
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Dosya 20MB'dan büyük olamaz")
    import json as _json
    try:
        data = _json.loads(content.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Geçersiz JSON: {e}")
    if data.get("version") != 1 or "payload" not in data:
        raise HTTPException(status_code=400, detail="Tanınmayan yedek formatı")

    uid = user.data_owner_id
    restored = 0
    collections = data.get("collections") or BACKUP_COLLECTIONS
    if mode == "replace":
        for c in collections:
            if c in BACKUP_COLLECTIONS:
                await db[c].delete_many({"user_id": uid})
    for c in collections:
        if c not in BACKUP_COLLECTIONS:
            continue
        records = data["payload"].get(c, [])
        if not records:
            continue
        new_records = []
        for r in records:
            r = {**r}
            r["user_id"] = uid
            if mode == "merge" or "id" not in r:
                r["id"] = str(uuid.uuid4())
            new_records.append(r)
        if new_records:
            await db[c].insert_many(new_records)
            restored += len(new_records)
    return {"ok": True, "restored": restored, "mode": mode}


async def _run_weekly_backups():
    logger.info("Running weekly auto-backup for all workspaces...")
    workspaces = await db.workspaces.find({}, {"_id": 0}).to_list(10000)
    for ws in workspaces:
        try:
            await _create_backup(ws["owner_user_id"], ws["workspace_id"], "auto")
        except Exception as e:
            logger.error(f"Backup failed for workspace {ws.get('workspace_id')}: {e}")
    logger.info(f"Weekly backup done for {len(workspaces)} workspaces.")


# ---------------- Excel/CSV Import ----------------
IMPORT_SCHEMAS = {
    "expenses": {
        "collection": "expenses",
        "columns": ["category", "description", "amount", "vat_rate", "date"],
        "required": ["category", "description", "amount", "date"],
        "amount_fields": ["amount", "vat_rate"],
        "date_fields": ["date"],
        "sample_row": ["Kira", "Ofis kirası Şubat", "12500.00", "20", "2026-02-01"],
    },
    "incomes": {
        "collection": "incomes",
        "columns": ["source", "description", "amount", "vat_rate", "date"],
        "required": ["source", "amount", "date"],
        "amount_fields": ["amount", "vat_rate"],
        "date_fields": ["date"],
        "sample_row": ["Satış", "Ürün satışı", "45000.00", "20", "2026-02-05"],
    },
    "checks": {
        "collection": "checks",
        "columns": ["type", "party", "amount", "due_date", "bank_name", "check_number", "status", "notes"],
        "required": ["type", "party", "amount", "due_date"],
        "amount_fields": ["amount"],
        "date_fields": ["due_date"],
        "sample_row": ["issued", "ABC Ltd", "15000.00", "2026-03-15", "Garanti BBVA", "1234567", "pending", ""],
        "enum": {"type": ["received", "issued"], "status": ["pending", "cleared", "bounced"]},
    },
    "promissory-notes": {
        "collection": "promissory_notes",
        "columns": ["type", "party", "amount", "due_date", "status", "notes"],
        "required": ["type", "party", "amount", "due_date"],
        "amount_fields": ["amount"],
        "date_fields": ["due_date"],
        "sample_row": ["received", "XYZ A.Ş.", "8500.00", "2026-03-20", "pending", ""],
        "enum": {"type": ["received", "issued"], "status": ["pending", "paid", "overdue"]},
    },
}


def _parse_iso_date(v) -> Optional[str]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if hasattr(v, "isoformat"):
        try:
            return v.isoformat()[:10]
        except Exception:
            pass
    s = str(v).strip()
    # Accept dd/mm/yyyy, dd.mm.yyyy, dd-mm-yyyy, yyyy-mm-dd
    for sep in ["/", ".", "-"]:
        if sep in s and len(s.split(sep)) == 3:
            parts = s.split(sep)
            try:
                if len(parts[0]) == 4:  # yyyy-mm-dd
                    y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                else:
                    d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
                return date(y, m, d).isoformat()
            except Exception:
                continue
    return None


def _read_rows(file_bytes: bytes, filename: str):
    name = (filename or "").lower()
    if name.endswith(".xlsx") or name.endswith(".xlsm"):
        from openpyxl import load_workbook
        wb = load_workbook(filename=io.BytesIO(file_bytes), data_only=True, read_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return [], []
        headers = [str(h).strip().lower() if h is not None else "" for h in rows[0]]
        data = []
        for r in rows[1:]:
            if all(c is None or str(c).strip() == "" for c in r):
                continue
            data.append({headers[i]: r[i] for i in range(min(len(headers), len(r)))})
        return headers, data
    else:
        # CSV
        text = file_bytes.decode("utf-8-sig", errors="replace")
        # Auto-detect delimiter
        delim = ";" if text.count(";") > text.count(",") else ","
        reader = csv.DictReader(io.StringIO(text), delimiter=delim)
        headers = [h.strip().lower() for h in (reader.fieldnames or [])]
        data = [{k.strip().lower(): v for k, v in row.items()} for row in reader if any((v or "").strip() for v in row.values())]
        return headers, data


@api_router.get("/import/{resource}/template")
async def import_template(resource: str, user: User = Depends(get_current_user)):
    schema = IMPORT_SCHEMAS.get(resource)
    if not schema:
        raise HTTPException(status_code=404, detail="Bilinmeyen kaynak")
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = resource
    ws.append(schema["columns"])
    ws.append(schema["sample_row"])
    # Header style
    from openpyxl.styles import Font, PatternFill
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="0F172A")
    for i, col in enumerate(schema["columns"], 1):
        ws.column_dimensions[chr(64 + i)].width = max(14, len(col) + 4)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"nakit-akis-sablon-{resource}.xlsx"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api_router.post("/import/{resource}")
async def import_file(resource: str, file: UploadFile = File(...), user: User = Depends(get_current_user)):
    schema = IMPORT_SCHEMAS.get(resource)
    if not schema:
        raise HTTPException(status_code=404, detail="Bilinmeyen kaynak")
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Dosya 5MB'dan büyük olamaz")

    try:
        headers, rows = _read_rows(content, file.filename or "")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Dosya okunamadı: {e}")

    missing_headers = [c for c in schema["required"] if c not in headers]
    if missing_headers:
        raise HTTPException(status_code=400, detail=f"Eksik kolonlar: {', '.join(missing_headers)}")

    inserted = 0
    errors = []
    docs = []
    for idx, row in enumerate(rows, start=2):  # start=2 because row 1 is header
        try:
            record = {"id": str(uuid.uuid4()), "user_id": user.data_owner_id,
                      "created_at": datetime.now(timezone.utc).isoformat()}
            for col in schema["columns"]:
                v = row.get(col)
                if v is None or (isinstance(v, str) and v.strip() == ""):
                    if col in schema["required"]:
                        raise ValueError(f"'{col}' zorunlu")
                    # Sensible defaults for optional fields
                    if col == "vat_rate":
                        record[col] = 20.0
                    elif col in schema["amount_fields"]:
                        record[col] = 0.0
                    else:
                        record[col] = ""
                    continue
                if col in schema["amount_fields"]:
                    try:
                        record[col] = float(str(v).replace(",", ".").replace(" ", ""))
                    except Exception:
                        raise ValueError(f"'{col}' geçersiz tutar: {v}")
                elif col in schema["date_fields"]:
                    d = _parse_iso_date(v)
                    if not d:
                        raise ValueError(f"'{col}' geçersiz tarih: {v}")
                    record[col] = d
                else:
                    record[col] = str(v).strip()
                    # Enum validation
                    if "enum" in schema and col in schema["enum"]:
                        if record[col].lower() not in schema["enum"][col]:
                            raise ValueError(f"'{col}' geçersiz değer: {v} (izin verilen: {', '.join(schema['enum'][col])})")
                        record[col] = record[col].lower()
            # Default status if not provided
            if resource == "checks" and not record.get("status"):
                record["status"] = "pending"
            if resource == "promissory-notes" and not record.get("status"):
                record["status"] = "pending"
            docs.append(record)
        except Exception as e:
            errors.append({"row": idx, "message": str(e)})

    if docs:
        await db[schema["collection"]].insert_many(docs)
        inserted = len(docs)

    return {"inserted": inserted, "errors": errors, "total_rows": len(rows)}



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


class Preferences(BaseModel):
    model_config = ConfigDict(extra="ignore")
    email_enabled: bool = True
    in_app_enabled: bool = True
    whatsapp_enabled: bool = False
    whatsapp_number: Optional[str] = None
    reminder_days: List[int] = Field(default_factory=lambda: [3, 1])
    notification_email: Optional[str] = None


DEFAULT_PREFS = {
    "email_enabled": True,
    "in_app_enabled": True,
    "whatsapp_enabled": False,
    "whatsapp_number": None,
    "reminder_days": [3, 1],
    "notification_email": None,
}


async def _get_prefs(user_id: str) -> dict:
    doc = await db.user_preferences.find_one({"user_id": user_id}, {"_id": 0})
    if not doc:
        return DEFAULT_PREFS.copy()
    return {**DEFAULT_PREFS, **{k: v for k, v in doc.items() if k in DEFAULT_PREFS}}


@api_router.get("/preferences", response_model=Preferences)
async def get_preferences(user: User = Depends(get_current_user)):
    prefs = await _get_prefs(user.user_id)
    return Preferences(**prefs)


@api_router.put("/preferences", response_model=Preferences)
async def update_preferences(payload: Preferences, user: User = Depends(get_current_user)):
    days = sorted({int(d) for d in payload.reminder_days if 0 < int(d) <= 60}) or [3, 1]
    # Normalize phone number to E.164-ish (basic)
    wnum = (payload.whatsapp_number or "").strip().replace(" ", "").replace("-", "")
    if wnum and not wnum.startswith("+"):
        wnum = "+" + wnum
    doc = {
        "email_enabled": bool(payload.email_enabled),
        "in_app_enabled": bool(payload.in_app_enabled),
        "whatsapp_enabled": bool(payload.whatsapp_enabled),
        "whatsapp_number": wnum or None,
        "reminder_days": days,
        "notification_email": (payload.notification_email or "").strip() or None,
    }

    # Check if user is enabling WhatsApp for the first time to send welcome
    previous = await db.user_preferences.find_one({"user_id": user.user_id}, {"_id": 0})
    should_send_welcome = (
        doc["whatsapp_enabled"] and wnum and
        (not previous or not previous.get("welcome_sent"))
    )

    await db.user_preferences.update_one(
        {"user_id": user.user_id},
        {"$set": {"user_id": user.user_id, **doc}},
        upsert=True,
    )

    if should_send_welcome and TWILIO_WHATSAPP_WELCOME_TEMPLATE_SID:
        ok = await _send_whatsapp(
            wnum,
            body=f"Nakit Akış'a hoş geldiniz {user.name}!",
            template_vars={"1": (user.name or "değerli kullanıcı")[:60]},
            template_sid=TWILIO_WHATSAPP_WELCOME_TEMPLATE_SID,
        )
        if ok:
            await db.user_preferences.update_one(
                {"user_id": user.user_id},
                {"$set": {"welcome_sent": True, "welcome_sent_at": datetime.now(timezone.utc).isoformat()}},
            )
    return Preferences(**doc)


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


async def _send_whatsapp(to_number: str, body: str, template_vars: Optional[dict] = None, template_sid: Optional[str] = None) -> bool:
    """Send WhatsApp message.
    - If template_vars is provided AND a template SID is available → send via approved template (works outside 24h window).
    - Else → freeform body (only works with sandbox or inside 24h customer service window).
    """
    if not _twilio_client or not TWILIO_WHATSAPP_FROM:
        logger.warning("Twilio not configured - skipping WhatsApp")
        return False
    sid = template_sid or TWILIO_WHATSAPP_TEMPLATE_SID
    to = to_number if to_number.startswith("whatsapp:") else f"whatsapp:{to_number}"
    try:
        def _send():
            if template_vars and sid:
                import json as _json
                return _twilio_client.messages.create(
                    from_=TWILIO_WHATSAPP_FROM,
                    to=to,
                    content_sid=sid,
                    content_variables=_json.dumps(template_vars),
                )
            return _twilio_client.messages.create(from_=TWILIO_WHATSAPP_FROM, to=to, body=body)
        msg = await asyncio.to_thread(_send)
        logger.info(f"WhatsApp sent to {to_number}: sid={msg.sid} template={bool(template_vars and sid)}")
        return True
    except Exception as e:
        logger.error(f"WhatsApp send failed to {to_number}: {e}")
        # If template fails (e.g., not approved yet), try freeform as fallback
        if template_vars and sid:
            try:
                def _fallback():
                    return _twilio_client.messages.create(from_=TWILIO_WHATSAPP_FROM, to=to, body=body)
                msg = await asyncio.to_thread(_fallback)
                logger.info(f"WhatsApp fallback (freeform) sent to {to_number}: sid={msg.sid}")
                return True
            except Exception as e2:
                logger.error(f"WhatsApp fallback also failed: {e2}")
        return False


def _tr_amount(v: float) -> str:
    s = f"{v:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _tr_date(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso).date()
        return dt.strftime("%d.%m.%Y")
    except Exception:
        return iso


def _build_template_vars_for_item(user_name: str, item: dict) -> dict:
    """Match template body:
    Merhaba {{1}}, ödemenizin vadesine {{2}} gün kaldı: {{3}} ({{4}}) Tutar: {{5}} ₺ Vade: {{6}}
    """
    kind = "Çek" if item["kind"] == "check" else "Senet"
    direction = "Alınan" if item["type"] == "received" else "Verilen"
    kind_label = f"{direction} {kind}"
    return {
        "1": user_name,
        "2": str(item["days_before"]),
        "3": item["party"][:60],
        "4": kind_label,
        "5": _tr_amount(item["amount"]),
        "6": _tr_date(item["due_date"]),
    }


def _render_whatsapp_text(user_name: str, items: List[dict]) -> str:
    tr_type = {"received": "Alacak", "issued": "Borç"}
    lines = [f"🔔 *Nakit Akış — Yaklaşan Ödemeler*", f"Merhaba {user_name}!", ""]
    for it in items:
        kind = "Çek" if it["kind"] == "check" else "Senet"
        emoji = "🔴" if it["type"] == "issued" else "🟢"
        lines.append(f"{emoji} *{it['party']}*")
        lines.append(f"   {kind} · {tr_type.get(it['type'])} · {it['amount']:,.2f} ₺")
        lines.append(f"   📅 {it['due_date']} · {it['days_before']} gün kaldı")
        lines.append("")
    lines.append("_Bu bildirim Nakit Akış tarafından otomatik gönderildi._")
    return "\n".join(lines)


REMINDER_DAYS = [3, 1]  # default fallback when user has no preferences


async def _run_reminders_for_user(user_doc: dict):
    uid = user_doc["user_id"]
    prefs = await _get_prefs(uid)
    if not prefs["in_app_enabled"] and not prefs["email_enabled"]:
        return {"created": 0, "email_sent": False}
    reminder_days = prefs.get("reminder_days") or REMINDER_DAYS

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
        if delta in reminder_days:
            # dedupe: one notification per (item, days_before)
            key = {"user_id": uid, "item_id": it["id"], "days_before": delta, "kind": it["_kind"]}
            existing = await db.notifications.find_one(key, {"_id": 0})
            if existing:
                continue
            if prefs["in_app_enabled"]:
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
    target_email = prefs.get("notification_email") or user_doc.get("email")
    if triggered and prefs["email_enabled"] and target_email:
        html = _render_email_html(user_doc.get("name") or "Kullanıcı", triggered)
        email_sent = await _send_email(
            target_email,
            f"Nakit Akış — {len(triggered)} yaklaşan ödeme",
            html,
        )
        if email_sent:
            item_ids = [t["id"] for t in triggered]
            await db.notifications.update_many(
                {"user_id": uid, "item_id": {"$in": item_ids}, "email_sent": False},
                {"$set": {"email_sent": True}},
            )

    whatsapp_sent = False
    wnum = prefs.get("whatsapp_number")
    if triggered and prefs.get("whatsapp_enabled") and wnum:
        # Send ONE template message per item (Meta template compliance)
        # Also send a summary freeform (works if 24h customer service window is open, otherwise silently ignored)
        sent_any = False
        user_name = user_doc.get("name") or "Kullanıcı"
        for it in triggered:
            vars_ = _build_template_vars_for_item(user_name, it)
            body = _render_whatsapp_text(user_name, [it])
            if await _send_whatsapp(wnum, body, template_vars=vars_):
                sent_any = True
        whatsapp_sent = sent_any
    return {"created": len(triggered), "email_sent": email_sent, "whatsapp_sent": whatsapp_sent}


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


@api_router.post("/notifications/test-whatsapp")
async def test_whatsapp(user: User = Depends(get_current_user)):
    prefs = await _get_prefs(user.user_id)
    wnum = prefs.get("whatsapp_number")
    if not wnum:
        raise HTTPException(status_code=400, detail="WhatsApp numarası tanımlı değil. Ayarlar sayfasında ekleyin.")
    if not _twilio_client:
        raise HTTPException(status_code=500, detail="Twilio yapılandırılmamış (backend .env)")
    # Use template with sample values (works outside 24h window when approved)
    sample_item = {
        "kind": "check", "type": "issued", "party": "Test Firma A.Ş.",
        "amount": 1234.56, "due_date": datetime.now(timezone.utc).date().isoformat(),
        "days_before": 1,
    }
    vars_ = _build_template_vars_for_item(user.name or "Test", sample_item)
    body = "Test WhatsApp mesajı - Nakit Akış"
    ok = await _send_whatsapp(wnum, body, template_vars=vars_)
    if not ok:
        raise HTTPException(status_code=502, detail="Mesaj gönderilemedi. Template henüz Meta onayı almadıysa 1-24 saat bekleyin.")
    return {"ok": True, "to": wnum}


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
    scheduler.add_job(_run_weekly_backups, CronTrigger(day_of_week="sun", hour=3, minute=0), id="weekly_backups", replace_existing=True)
    scheduler.start()
    logger.info("Reminder scheduler started (daily at 06:00 UTC / 09:00 TR). Weekly backups: Sun 03:00 UTC.")


@app.on_event("shutdown")
async def shutdown_db_client():
    try:
        scheduler.shutdown(wait=False)
    except Exception:
        pass
    client.close()
