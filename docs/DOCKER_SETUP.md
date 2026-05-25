# Docker Compose Setup Guide

## Overview

PropOps runs locally with one command. This guide assumes you have Docker and Docker Compose installed.

### What's Included

- **PostgreSQL 16**: Database with automatic schema initialization
- **FastAPI Backend**: Python API on port 8000, hot-reload enabled
- **Next.js Frontend**: React SPA on port 3000, hot-reload enabled
- **Adminer**: Database UI on port 8081 (optional, for debugging)

## Quick Start (3 steps)

### 1. Clone & Setup

```bash
git clone <repo>
cd propops
cp .env.example .env
```

### 2. Start Everything

```bash
docker-compose up --build
```

On **first run**, this will:
- Create PostgreSQL container with schema from `backend/infrastructure/init.sql`
- Install Python dependencies
- Install Node dependencies
- Start both services with hot reload

**Expected output:**
```
propops-db       | database system is ready to accept connections
propops-api      | INFO:     Application startup complete
propops-web      | ▲ Next.js 15.0.3
propops-web      | - Local:        http://localhost:3000
```

### 3. Open in Browser

- **Frontend (Approval Queue)**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs (Swagger)
- **Database UI**: http://localhost:8081
  - Server: `postgres`
  - User: `postgres`
  - Password: `postgres`
  - Database: `propops`

## Common Tasks

### View Logs

```bash
# All services
docker-compose logs -f

# Just backend
docker-compose logs -f backend

# Just frontend
docker-compose logs -f frontend

# Just database
docker-compose logs -f postgres
```

### Check Health

```bash
make health
```

Or manually:
```bash
# Backend API
curl http://localhost:8000/api/v1/health

# Frontend
curl http://localhost:3000
```

### Stop Services

```bash
docker-compose down
```

This stops containers but preserves database volume.

### Reset Database

```bash
docker-compose down -v
docker-compose up --build
```

Or use the shortcut:
```bash
make db-reset
```

### Run Backend Tests

```bash
docker-compose exec backend pytest tests/ -v
```

### Access Database Shell

```bash
docker-compose exec postgres psql -U postgres -d propops
```

Example queries:
```sql
-- List organizations
SELECT id, name, plan FROM organizations;

-- List incidents
SELECT id, title, urgency, status, created_at FROM incidents ORDER BY created_at DESC LIMIT 10;

-- List pending drafts
SELECT id, subject, status FROM ai_drafts WHERE status = 'pending';
```

### Access Backend Shell

```bash
docker-compose exec backend bash

# Inside container:
python -m pytest tests/
```

## Environment Variables

### Required (Fill In .env)

- `ANTHROPIC_API_KEY` — Claude API key from Anthropic
- `IMAP_USERNAME` / `IMAP_PASSWORD` — Gmail or Outlook credentials
- `SMTP_USERNAME` / `SMTP_PASSWORD` — SMTP credentials

### Optional (Defaults Provided)

- `IMAP_HOST` — defaults to `imap.gmail.com`
- `SMTP_HOST` — defaults to `smtp.gmail.com`
- `ENVIRONMENT` — defaults to `development`
- `LOG_LEVEL` — defaults to `INFO`

### Auto-Set by Docker Compose

- `DATABASE_URL` — always set to `postgresql+asyncpg://postgres:postgres@postgres:5432/propops`
- `NEXT_PUBLIC_API_URL` — always set to `http://localhost:8000`

## Hot Reload

Both backend and frontend support hot reload during development:

### Backend

Changes to Python files in `backend/` are automatically detected by uvicorn.

```bash
# Edit backend/api/routes/incidents.py
# Save → Backend restarts in ~1 second
```

### Frontend

Changes to TypeScript/TSX files in `frontend/` trigger Next.js HMR.

```bash
# Edit frontend/app/page.tsx
# Save → Frontend hot reloads in ~100ms
```

## Troubleshooting

### "Port 8000 already in use"

```bash
# Find what's using port 8000
lsof -i :8000

# Kill it
kill -9 <PID>

# Or change docker-compose.yml port mapping:
# ports:
#   - "8001:8000"  # Use 8001 instead
```

### "Cannot connect to Docker daemon"

```bash
# Make sure Docker is running:
docker version

# On Mac/Windows, open Docker Desktop application
```

### "PostgreSQL connection refused"

```bash
# Check if postgres service is running
docker-compose ps

# If postgres is down:
docker-compose restart postgres

# Check logs:
docker-compose logs postgres
```

### "Next.js build fails in docker"

```bash
# Rebuild frontend image
docker-compose build frontend --no-cache
docker-compose up frontend
```

### Database won't initialize

```bash
# Check if init.sql was applied
docker-compose exec postgres psql -U postgres -d propops -c "\dt"

# Reinit from scratch
docker-compose down -v
docker-compose up
```

## Performance Notes

- **First boot**: 2–3 minutes (installs Python/Node deps)
- **Subsequent boots**: <10 seconds
- **Hot reload (backend)**: ~1 second
- **Hot reload (frontend)**: ~100ms
- **Database queries**: <100ms typical

## Data Persistence

Database data is stored in a Docker named volume `postgres_data`:

```bash
# View volumes
docker volume ls | grep propops

# Inspect volume
docker volume inspect postgres_data

# Remove all PropOps volumes
docker volume rm postgres_data
```

To keep data across `docker-compose down`, the volume is preserved. Only `docker-compose down -v` removes it.

## Production Builds

These Dockerfiles are NOT suitable for production. For production:

1. Use `docker build -f frontend/Dockerfile.prod` for optimized Next.js builds
2. Use environment-specific secrets management (Vault, AWS Secrets Manager)
3. Add reverse proxy (nginx) in front
4. Use managed database (Supabase, AWS RDS, Railway)
5. Add proper health checks and orchestration (Kubernetes, Docker Swarm, or container services)

See `docs/DEPLOYMENT.md` for production guidance.

## Getting Help

- **Backend logs**: `docker-compose logs -f backend`
- **Frontend logs**: `docker-compose logs -f frontend`
- **Database logs**: `docker-compose logs -f postgres`
- **All logs**: `docker-compose logs -f`

---

Last updated: 2025-01-10
---