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
Vendor Outreach (Phase 2)
```

## Phase 1 MVP — Inbox Triage Wedge

- [ ] Inbox ingestion (IMAP/Gmail/Outlook)
- [ ] AI classification + urgency scoring
- [ ] Draft reply generation
- [ ] Human approval queue (web UI)
- [ ] Incident state machine (OPEN → RESOLVED)
- [ ] Audit log

## Tech Stack

- **Backend**: FastAPI (Python)
- **Frontend**: Next.js + Tailwind + shadcn/ui
- **Database**: PostgreSQL (Supabase)
- **AI**: Claude Haiku (triage) + Claude Sonnet (drafting)
- **Email**: IMAP + Gmail API + Outlook API
- **Deploy**: Vercel (frontend) + Railway (backend)

## ICP

Property management companies:
- 50–500 units
- Toronto/GTA first, then Ontario, Canada, USA
- 2–25 employees
- Email-heavy workflows

## Pricing

- Beta: Free
- Paid: \–2/unit/month
- Later: hybrid base + workflow usage

## Getting Started

```bash
cp .env.example .env
# fill in your values

# Backend
cd backend && pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
cd frontend && npm install && npm run dev
```

---
*Built by ANVIL · Managed by NEXUS · Reviewed by FORGE · LN Sols Pvt Ltd*