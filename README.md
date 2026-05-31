# PropOps

**AI Operational Middleware for Property Managers.**

PropOps automates the inbox → triage → draft → approve → reply loop so property managers spend minutes, not hours, on tenant email.

---

## What it does

1. **Polls your inbox** every 60 s via IMAP
2. **Triages** each email with Claude Haiku (category + urgency in < 1 s)
3. **Drafts** a professional reply with Claude Sonnet (NEVER admits liability)
4. **Queues** the draft for your 1-click approval in the dashboard
5. **Sends** the approved reply via SMTP and marks the incident closed

---

## Quickstart (Docker — recommended)

```bash
cp backend/.env.example backend/.env
# Fill in ANTHROPIC_API_KEY, IMAP_*, SMTP_*, FERNET_KEY at minimum

docker compose up --build
```

- **Dashboard:** http://localhost:3000
- **API docs:** http://localhost:8000/docs
- **DB admin:** http://localhost:8080

### Generate FERNET_KEY

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## Phase 2 setup (Tenants / Vendors / Onboarding)

After your first `docker compose up`:

1. Visit http://localhost:3000/onboarding — enter your IMAP/SMTP details
2. Copy the `org_id` returned and add it to `frontend/.env.local`:
   ```
   NEXT_PUBLIC_DEFAULT_ORG_ID=<paste here>
   ```
3. Import tenants at http://localhost:3000/tenants (CSV upload supported)
4. Add vendors at http://localhost:3000/vendors

---

## Stack

| Layer | Tech |
|-------|------|
| Backend | FastAPI · SQLAlchemy 2 async · PostgreSQL 16 · Alembic |
| AI | Anthropic Claude (Haiku triage, Sonnet drafts) |
| Frontend | Next.js 14 · Tailwind CSS |
| Email | IMAP (imaplib) · SMTP |
| Infra | Docker Compose |

---

## Project structure

```
backend/
  api/routes/      — FastAPI routers (incidents, approvals, dashboard, tenants, vendors, onboarding)
  ai/              — Claude triage + draft agents
  models/          — SQLAlchemy models
  services/        — inbox poller, email sender, context resolver, vendor notifier
  core/            — database, config, encryption
  alembic/         — DB migrations
frontend/
  app/             — Next.js app router pages
```

---

## Running tests

```bash
cd backend && pip install -r requirements.txt -r requirements-dev.txt
pytest tests/ -v
```

---

## Phase roadmap

- ✅ **Phase 1** — Core pipeline: IMAP → triage → draft → approve → send
- ✅ **Phase 2** — Dashboard, tenant/unit management, vendor management, org onboarding
- 🔜 **Phase 3** — Auth (Clerk/Auth.js), multi-org isolation, billing, mobile push

---

*Built by LN Sols · lnsols.com*
