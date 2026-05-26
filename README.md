# PropOps — AI Operational Middleware for Property Managers

**LN Sols Pvt Ltd** | Built with Project Helix

---

## What Is This

PropOps is the AI operations layer for property management companies.

It does NOT replace AppFolio, Buildium, or Yardi.  
It sits **on top of them** and solves coordination chaos — the thing legacy PM software never solved.

## The Problem It Solves

- Overwhelmed inboxes (tenant + vendor emails 24/7)
- Vendor coordination chaos (quotes, scheduling, follow-ups)
- Turnover orchestration (cleaning → repairs → listing — all manual today)
- Fragmented communication across email, SMS, portals

## How It Works

```
Inbound Email/SMS
      ↓
AI Triage (classify + urgency)
      ↓
Incident Created
      ↓
Draft Reply Generated
      ↓
Property Manager Approves (1 click)
      ↓
SMTP Send (Auto)
      ↓
Vendor Outreach (Phase 2)
```

## Phase 1 MVP — Inbox Triage Wedge

- [x] Inbox ingestion (IMAP/Gmail/Outlook)
- [x] AI classification + urgency scoring
- [x] Draft reply generation
- [x] Human approval queue (web UI)
- [x] **Email sending via SMTP** ← NEW
- [x] Incident state machine (OPEN → RESOLVED)
- [x] Audit log

## Tech Stack

- **Backend**: FastAPI (Python)
- **Frontend**: Next.js + Tailwind + shadcn/ui
- **Database**: PostgreSQL (Supabase)
- **AI**: Claude Haiku (triage) + Claude Sonnet (drafting)
- **Email**: IMAP + Gmail API + Outlook API + SMTP
- **Deploy**: Vercel (frontend) + Railway (backend)

## ICP

Property management companies:
- 50–500 units
- Toronto/GTA first, then Ontario, Canada, USA
- 2–25 employees
- Email-heavy workflows

## Pricing

- Beta: Free
- Paid: $2/unit/month
- Later: hybrid base + workflow usage

## Getting Started

```bash
cp .env.example .env
# fill in your SMTP credentials (Gmail App Password recommended)

# Backend
cd backend && pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev
```

### Setting up Gmail SMTP

1. Enable 2-Step Verification on your Google account
2. Generate an App Password: https://myaccount.google.com/apppasswords
3. Use the 16-character password in `SMTP_PASSWORD`

---
*Built by ANVIL · Managed by NEXUS · Reviewed by FORGE · LN Sols Pvt Ltd*
---