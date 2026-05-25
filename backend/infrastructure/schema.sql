-- PropOps PostgreSQL Schema — Phase 1: Inbox Triage Wedge
-- Created: 2025
-- DB: PostgreSQL 14+
-- Note: Uses gen_random_uuid() (requires pgcrypto extension)

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── Organizations (PM companies) ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS organizations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,
    email_domain    VARCHAR(255),
    plan            VARCHAR(50) DEFAULT 'beta'
                    CHECK (plan IN ('beta', 'starter', 'pro')),
    unit_count      INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_organizations_deleted 
    ON organizations(deleted_at) WHERE deleted_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_organizations_email_domain 
    ON organizations(email_domain);


-- ── Properties (buildings) ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS properties (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    name            VARCHAR(255) NOT NULL,
    address         TEXT,
    city            VARCHAR(100),
    province        VARCHAR(50),
    postal_code     VARCHAR(20),
    unit_count      INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_properties_org 
    ON properties(org_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_properties_deleted 
    ON properties(deleted_at) WHERE deleted_at IS NULL;


-- ── Units (tenant-linked units with contact info) ──────────────────────────
CREATE TABLE IF NOT EXISTS units (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id     UUID NOT NULL REFERENCES properties(id) ON DELETE RESTRICT,
    unit_number     VARCHAR(50) NOT NULL,
    tenant_name     VARCHAR(255),
    tenant_email    VARCHAR(255),
    tenant_phone    VARCHAR(50),
    lease_start     DATE,
    lease_end       DATE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_units_property 
    ON units(property_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_units_tenant_email 
    ON units(tenant_email) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_units_deleted 
    ON units(deleted_at) WHERE deleted_at IS NOT NULL;


-- ── Incidents (unified operational thread / UOTL) ──────────────────────────
-- State machine: OPEN → PENDING_APPROVAL → DISPATCH_READY → DISPATCHED → 
--                IN_PROGRESS → RESOLVED → CLOSED
CREATE TABLE IF NOT EXISTS incidents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    property_id     UUID REFERENCES properties(id) ON DELETE SET NULL,
    unit_id         UUID REFERENCES units(id) ON DELETE SET NULL,
    thread_id       UUID NOT NULL DEFAULT gen_random_uuid(),
    title           VARCHAR(500) NOT NULL,
    category        VARCHAR(100),
                    CHECK (category IS NULL OR category IN ('maintenance', 'billing', 'noise', 'lease', 'move_in', 'move_out', 'general')),
    urgency         VARCHAR(50) DEFAULT 'MEDIUM'
                    CHECK (urgency IN ('EMERGENCY', 'HIGH', 'MEDIUM', 'LOW')),
    status          VARCHAR(50) DEFAULT 'OPEN'
                    CHECK (status IN ('OPEN', 'PENDING_APPROVAL', 'DISPATCH_READY', 'DISPATCHED', 'IN_PROGRESS', 'RESOLVED', 'CLOSED')),
    ai_summary      TEXT,
    