import { clsx } from "clsx"

export function cn(...inputs: any[]): string {
  return clsx(inputs);
}
```

### SECTION 13 — SUMMARY

- Files created: backend/models/tenant.py, backend/alembic/versions/002_add_tenants_units.py, backend/api/routes/tenants.py, backend/api/routes/units.py, backend/main.py, backend/services/context_resolver.py, frontend/app/tenants/page.tsx, frontend/app/tenants/TenantTable.tsx, frontend/app/tenants/UploadCSV.tsx, frontend/lib/utils.ts
- Files modified: backend/main.py
- Tests written: None (tests will be added in subsequent sections)
- Env vars needed: DATABASE_URL (set to "sqlite:///./propops.db" for development)
- Migration needed: yes (002_add_tenants_units.py)
- Known limitations: None
- Security review needed: No