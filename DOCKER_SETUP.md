# PropOps Docker Compose Setup

## Quick Start

```bash
# 1. Clone repo and navigate
git clone https://github.com/lnsolspvtltd/propops.git
cd propops

# 2. Copy environment template
cp .env.example .env

# 3. Edit .env with your API keys (optional for basic testing)
nano .env

# 4. Start everything with one command
docker-compose up --build

# Wait for services to initialize (~30 seconds)
```

Services will be available at:
- **Backend API**: http://localhost:8000
- **Frontend**: http://localhost:3000
- **Adminer (DB UI)**: http://localhost:8080
- **API Health**: http://localhost:8000/api/v1/health

---

## What Happens on First Run

1. **PostgreSQL** starts and applies schema from `backend/infrastructure/schema.sql`
2. **Backend** waits for Postgres health check, then applies migrations if needed
3. **Frontend** starts Next.js dev server (hot reload enabled)
4. **Adminer** UI available for database browsing

---

## Common Commands

### Start services
```bash
docker-compose up --build
```

### View logs
```bash
# All services
docker-compose logs -f

# Single service
docker-compose logs -f backend
docker-compose logs -f frontend
docker-compose logs -f postgres
```

### Stop services
```bash
docker-compose down
```

### Clean everything (including data)
```bash
docker-compose down -v
```

### Access database via psql
```bash
docker-compose exec postgres psql -U postgres -d propops
```

### Access backend shell
```bash
docker-compose exec backend bash
```

### Run backend tests
```bash
docker-compose exec backend pytest -v
```

### Test an email submission
```bash
curl -X POST http://localhost:8000/api/v1/inbox/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "sender": "tenant@example.com",
    "subject": "No hot water in unit 101",
    "body": "We have no hot water since yesterday. This is urgent!",
    "org_id": "00000000-0000-0000-0000-000000000001"
  }'
```

---

## Troubleshooting

### Port already in use
```bash
# Find process using port 3000
lsof -i :3000
# Find process using port 8000
lsof -i :8000
# Find process using port 5432
lsof -i :5432

# Kill process (example for port 3000)
kill -9 <PID>
```

### Database connection refused
```bash
# Check if postgres is healthy
docker-compose ps

# View postgres logs
docker-compose logs postgres

# Rebuild postgres only
docker-compose up -d postgres --build
```

### Frontend can't connect to backend
```bash
# Ensure NEXT_PUBLIC_API_URL=http://localhost:8000 in .env
# If inside Docker containers, use http://backend:8000 instead

# Test backend is accessible
curl http://localhost:8000/api/v1/health
```

### Hot reload not working
```bash
# Volume mounts need proper permissions
# On Linux: ensure file ownership is correct
ls -la backend/

# Restart with full rebuild
docker-compose down -v
docker-compose up --build
```

### PostgreSQL data lost
```bash
# Data is persisted in named volume 'postgres_data'
# To preserve data when stopping:
docker-compose down  # keeps volume

# To delete everything including data:
docker-compose down -v
```

---

## Environment Variables

See `.env.example` for all available variables:

**Critical for local dev:**
- `DATABASE_URL` — auto-constructed from DB_USER/PASSWORD/NAME
- `ANTHROPIC_API_KEY` — required for AI triage/drafting (get from [console.anthropic.com](https://console.anthropic.com))

**Optional (set to empty for mock):**
- `IMAP_USERNAME`, `IMAP_PASSWORD` — email ingestion
- `SMTP_USERNAME`, `SMTP_PASSWORD` — outbound email
- `TWILIO_*` — SMS support

**Frontend:**
- `NEXT_PUBLIC_API_URL` — backend URL (http://localhost:8000 for local)

---

## Docker Compose Architecture

```
┌─────────────────────────────────────────────┐
│       Docker Network: propops-network       │
├─────────────────────────────────────────────┤
│                                             │
│  ┌──────────────┐  ┌──────────────┐       │
│  │   Frontend   │  │   Backend    │       │
│  │ (Next.js)    │  │  (FastAPI)   │       │
│  │ :3000        │  │  :8000       │       │
│  └──────────────┘  └──────────────┘       │
│                           │                │
│                    depends_on              │
│                    (health)                │
│                           │                │
│  ┌──────────────┐  ┌──────────────┐       │
│  │   Adminer    │  │  PostgreSQL  │       │
│  │   (DB UI)    │  │  (Database)  │       │
│  │   :8080      │  │  :5432       │       │
│  │              │  │ volume:      │       │
│  │              │  │ postgres_data│       │
│  └──────────────┘  └──────────────┘       │
│                                             │
└─────────────────────────────────────────────┘
```

---

## File Structure

```
propops/
├── docker-compose.yml          # Main composition
├── docker-compose.override.yml # Local overrides (not committed)
├── .env.example                # Template variables
├── .env                        # Local secrets (gitignored)
├── Makefile                    # Convenience commands
│
├── backend/
│   ├── Dockerfile              # FastAPI image build
│   ├── main.py                 # FastAPI entry point
│   ├── requirements.txt         # Python dependencies
│   ├── core/
│   │   ├── config.py           # Settings from env vars
│   │   └── database.py         # SQLAlchemy + async
│   ├── infrastructure/
│   │   └── schema.sql          # PostgreSQL schema (auto-applied)
│   ├── models/
│   ├── services/
│   └── api/
│       └── routes/
│
├── frontend/
│   ├── Dockerfile              # Next.js image build
│   ├── package.json            # Node dependencies
│   ├── next.config.ts          # Next.js config
│   ├── app/                    # App Router pages
│   └── components/
│
└── DOCKER_SETUP.md             # This file
```

---

## Security Notes

- **.env is gitignored** — never commit secrets
- **Non-root users** in containers (appuser for backend, nextjs for frontend)
- **Health checks** prevent dependent services from starting until deps are ready
- **Named volumes** for data persistence — survives container restarts
- **Bridge network** isolates services from host network by default

---

## Next Steps

1. ✅ Run `docker-compose up --build`
2. Open http://localhost:3000 to see approval queue UI
3. Test with `curl` command in Troubleshooting section
4. Check logs: `docker-compose logs -f`
5. View database: http://localhost:8080 (Adminer)

---

**Questions?** Check logs: `docker-compose logs -f [service]`
---
EOF
---