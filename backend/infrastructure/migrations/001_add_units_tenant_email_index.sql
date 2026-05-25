"""
Alembic migration: Add index on units.tenant_email for context resolution performance.

Performance requirement: Context resolution lookup must complete in <50ms.
This index enables O(log n) lookup on exact email match.

Migration: Creates index on units(tenant_email) scoped by org via property_id.
"""

-- Index for exact email lookup (case-insensitive via function index)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_units_tenant_email_lower
    ON units (LOWER(tenant_email))
    WHERE tenant_email IS NOT NULL;

-- Composite index for org-scoped lookup (units.property_id → properties.org_id)
-- This helps the resolver query that joins Property to filter by org_id
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_units_property_id_email
    ON units (property_id, LOWER(tenant_email))
    WHERE tenant_email IS NOT NULL;

-- Comment for documentation
COMMENT ON INDEX idx_units_tenant_email_lower IS 
    'Enables fast tenant email lookup for context resolution. Case-insensitive.';
