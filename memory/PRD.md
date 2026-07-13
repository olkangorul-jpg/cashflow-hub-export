# Nakit Akış (Cash Flow Management) - PRD

## Problem Statement (Original, Turkish)
> Çekleri, aşacakları, giderleri, banka hesaplarını ve yaklaşan ödemeleri tek ekranda yönetebileceğim bir nakit akış yönetim uygulaması oluştur.

## User Personas
- Small business owners / freelancers in Turkey needing check & promissory-note visibility
- Finance managers tracking upcoming obligations and receivables

## Core Requirements
- Google login (Emergent OAuth)
- Manage bank accounts, checks (alınan/verilen), promissory notes (alacak/borç), expenses, incomes
- Upcoming payments view (next 30 days + monthly groups)
- Dashboard: total balance, upcoming in/out, monthly income vs expense chart, expense category breakdown
- CSV export for all lists
- TRY currency, Turkish UI, light theme

## Implemented (2026-02)
- FastAPI backend with per-user CRUD + dashboard + CSV export
- Emergent Google OAuth session flow (httpOnly cookie + Bearer fallback)
- React frontend (Manrope + IBM Plex Sans, Swiss high-contrast palette)
- Pages: Login, Dashboard, Bank Accounts, Checks, Promissory Notes, Expenses, Incomes, Upcoming Payments
- Recharts monthly bar + category donut
- Sonner toasts, Shadcn UI dialogs/tables/tabs/selects
- Testing agent iteration_1: 100% backend & frontend pass

## Backlog
- P1: Edit/delete UI polish testing coverage, PDF export, filter by date range
- P1: Currency multi-support (USD/EUR toggle)
- P2: Email/browser notifications for due payments (D-3, D-1)
- P2: Bank statement import (OFX/CSV)
- P2: Team sharing (multi-user org)

## Next Actions
- Gather user feedback on layout density
- Consider tax reports (KDV) breakdown per period
