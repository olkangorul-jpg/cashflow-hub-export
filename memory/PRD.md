# Nakit Akış (Cash Flow Management) - PRD

## Problem Statement (Original, Turkish)
> Çekleri, aşacakları, giderleri, banka hesaplarını ve yaklaşan ödemeleri tek ekranda yönetebileceğim bir nakit akış yönetim uygulaması oluştur.

## User Personas
- Small business owners / freelancers in Turkey needing check & promissory-note visibility
- Finance managers tracking upcoming obligations and receivables
- Teams collaborating on cash-flow (multi-user workspaces with roles)

## Core Requirements
- Google login (Emergent OAuth)
- Manage bank accounts, checks (alınan/verilen), promissory notes (alacak/borç), expenses, incomes
- Upcoming payments view (next 30 days + monthly groups)
- Dashboard with charts (balance, upcoming, monthly income vs expense, category breakdown)
- Excel/CSV/PDF export
- TRY (₺) currency, Turkish UI, light theme
- Multi-user workspaces with roles: owner / editor / viewer

## Implemented
- FastAPI + MongoDB backend, React + Shadcn UI frontend
- Emergent Google OAuth (httpOnly cookie + Bearer fallback)
- CRUD: bank accounts, checks, promissory notes, expenses, incomes
- Dashboard: totals, upcoming in/out, monthly bar chart, category donut
- CSV/Excel/PDF export + Excel import for expenses/incomes/checks
- KDV/VAT period reports (PDF + XLSX)
- Reminders: in-app bell + Resend email at D-3/D-1, daily APScheduler 09:00 TR
- Twilio WhatsApp reminders + Welcome template (Meta-approved HX templates)
- Multi-workspace tenancy + invite flow with roles (owner/editor/viewer)
- Automated weekly JSON backups + manual backup/restore/download
- **2026-02: Backend viewer-role authorization** — `require_write(user)` applied to all 18 mutation endpoints (bank_accounts, checks, notes, expenses, incomes, backups, import). 35/35 pytest role-auth tests green. Closes iteration 9 security gap.

## Deployment
- Live production: Emergent-hosted, mapped to custom domain `contact.artemarble.com.tr`.
- SSL: provisioned automatically by Emergent after DNS is linked via the Deployments → Link domain (Entri) flow. See support agent guidance in session history.

## Backlog
- P2: MongoDB TTL index on `user_sessions.expires_at` for auto-cleanup
- P2: Refactor `/app/backend/server.py` (2200+ lines) into `routes/`, `services/`, `models/`
- P2: Switch `require_write` from ad-hoc call to declarative FastAPI dependency (e.g. `Depends(require_write_user)`) so authorization is impossible to forget
- P2: Move backup restore endpoints' inline viewer check to shared `require_write` helper (consistency)
- P2: Currency multi-support (USD/EUR toggle)
- P2: Bank statement import (OFX/CSV)
- P3: Browser push notifications

## Next Actions
- User to complete DNS re-link via Emergent Deployments UI for SSL provisioning on `contact.artemarble.com.tr`
- Consider making `require_write` a FastAPI dependency (declarative auth) — improves auditability
