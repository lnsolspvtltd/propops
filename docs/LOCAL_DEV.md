# Local Development Guide

## First-Time Setup

### 1. Prerequisites

- Docker & Docker Compose (v2.0+)
- Git
- Code editor (VS Code recommended)

### 2. Clone Repository

```bash
git clone <repo-url>
cd propops
```

### 3. Environment Configuration

```bash
cp .env.example .env
```

Then edit `.env` and fill in:
- `ANTHROPIC_API_KEY` (get from Claude API dashboard)
- `IMAP_USERNAME` / `IMAP_PASSWORD` (optional for dev)
- `SMTP_USERNAME` / `SMTP_PASSWORD` (optional for dev)

### 4. Start Services

```bash
docker-compose up --build
```

Wait for output showing:
```
propops-api      | INFO:     Application startup complete
propops-web      | Ready in 1.234s
```

### 5. Test Everything

Open in browser:
- Frontend: http://localhost:3000 ✅
- API Docs: http://localhost:8000/docs ✅
- Database UI: http://localhost:8081 ✅

## Daily Workflow

### Starting Development Session

```bash
# Terminal 1: Start all services
docker-compose up

# Terminal 2: Watch logs
docker-compose logs -f
```

### Making Code Changes

**Backend changes** (Python):
```bash
# Edit backend/api/routes/incidents.py
# Save → uvicorn reloads automatically (~1s)
# Test at http://localhost:8000/docs
```

**Frontend changes** (TypeScript/React):
```bash
# Edit frontend/app/page.tsx
# Save → Next.js hot reload (~100ms)
# Refresh browser at http://localhost:3000
```

**Schema changes** (SQL):
```bash
# Edit backend/infrastructure/init.sql
docker-compose down -v
docker-compose up --build
```

### Testing

```bash
# Backend unit tests
docker-compose exec backend pytest tests/ -v

# Backend with coverage
docker-compose exec backend pytest tests/ --cov=backend --cov-report=html

# Frontend tests (when added)
docker-compose exec frontend npm test
```

### Database Inspection

```bash
# Interactive SQL shell
docker-compose exec postgres psql -U postgres -d propops

# Example queries:
SELECT id, title, urgency FROM incidents ORDER BY created_at DESC LIMIT 5;
SELECT id, status FROM ai_drafts WHERE status = 'pending';
```

Or use Adminer UI at http://localhost:8081

## Project Structure

```
propops/
├── backend/
│   ├── main.py                      # FastAPI entry point
│   ├── Dockerfile                   # Backend Docker image
│   ├── requirements.txt             # Python dependencies
│   ├── core/
│   │   ├── config.py               # Environment config
│   │   └── database.py             # SQLAlchemy setup
│   ├── models/
│   │   └── incident.py             # Database models
│   ├── api/
│   │   └── routes/                 # API endpoints
│   ├── ai/
│   │   ├── triage_agent.py        # AI classification
│   │   └── draft_agent.py         # AI reply generation
│   ├── services/
│   │   └── inbox_poller.py        # Email ingestion
│   ├── infrastructure/
│   │   └── init.sql               # Database schema
│   └── tests/                       # Backend tests
├── frontend/
│   ├── Dockerfile                   # Frontend Docker image
│   ├── package.json                # Node dependencies
│   ├── app/
│   │   ├── layout.tsx              # Root layout
│   │   ├── page.tsx                # Approval queue UI
│   │   └── globals.css             # Tailwind styles
│   └── components/                  # React components
├── docker-compose.yml               # Service orchestration
├── .env.example                     # Environment template
└── Makefile                         # Development shortcuts
```

## Common Commands

```bash
# Start/stop
docker-compose up        # Start all services
docker-compose down      # Stop all services
docker-compose restart   # Restart all services

# Logs
docker-compose logs -f backend    # Backend logs
docker-compose logs -f frontend   # Frontend logs
docker-compose logs -f postgres   # Database logs

# Shell access
docker-compose exec backend bash   # Backend shell
docker-compose exec frontend sh    # Frontend shell
docker-compose exec postgres psql -U postgres -d propops  # Database CLI

# Database
docker-compose exec backend alembic upgrade head  # Run migrations (when added)
docker-compose exec postgres psql -U postgres -d propops -c "SELECT version();"

# Cleanup
docker-compose down -v    # Stop and remove volumes (wipes database)
docker volume prune       # Remove unused Docker volumes
```

## Code Style & Standards

### Python (Backend)

- Use type hints on all functions
- Docstrings on public functions
- PEP 8 style guide
- Black formatter (if added)
- mypy type checking (if added)

Example:
```python
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

async def get_incident(
    db: AsyncSession,
    incident_id: str,
) -> Optional[Incident]:
    """Fetch a single incident by ID."""
    result = await db.execute(
        select(Incident).where(Incident.id == uuid.UUID(incident_id))
    )
    return result.scalar_one_or_none()
```

### TypeScript/React (Frontend)

- Enable TypeScript strict mode
- No `any` types (use `unknown` with type guards)
- Use functional components + hooks
- Prefer descriptive variable names

Example:
```typescript
import { useState, useEffect } from "react"

interface Draft {
  draft_id: string
  subject: string
  body: string
  status: "pending" | "approved" | "rejected"
}

export function DraftList(): JSX.Element {
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchDrafts()
  }, [])

  return <div>{/* JSX */}</div>
}
```

## Debugging Tips

### Backend

```bash
# Enable SQL query logging
# In backend/core/config.py, set:
# engine = create_async_engine(..., echo=True)

# Or set environment variable:
export SQLALCHEMY_ECHO=1
docker-compose up

# Watch logs while making requests
docker-compose logs -f backend
```

### Frontend

```bash
# Browser DevTools
# 1. Open http://localhost:3000
# 2. Press F12 or Cmd+Option+I
# 3. Check Console tab for errors
# 4. Check Network tab to see API calls

# React DevTools (if installed)
# https://chrome.google.com/webstore/detail/react-developer-tools/...
```

### Database