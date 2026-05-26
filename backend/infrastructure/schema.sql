-- PropOps PostgreSQL Schema — Phase 1: Inbox Triage Wedge
--
-- REFERENCE ONLY: This file is for documentation and local development.
-- CANONICAL SOURCE: backend/alembic/versions/001_initial_phase1_schema.py
--
-- In production, ALL schema changes must go through Alembic migrations.
-- Running raw SQL against this file will cause drift. Use:
--   alembic upgrade head
--
-- Created: 2025
-- DB: PostgreSQL 14+
-- Note: Uses gen_random_uuid() (requires pgcrypto extension)

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── Organizations (PM companies) ─────────────────────────────────────────────
-- Root tenant: PM companies subscribing to PropOps
CREATE TABLE IF NOT EXISTS organizations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,
    email_domain    VARCHAR(255),
    plan            VARCHAR(50) DEFAULT 'beta' NOT NULL
                    CHECK (plan IN ('beta', 'starter', 'pro')),
    unit_count      INTEGER DEFAULT 0 NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ  -- soft delete (NULL = active)
);

CREATE INDEX IF NOT EXISTS idx_organizations_deleted 
    ON organizations(deleted_at) WHERE deleted_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_organizations_email_domain 
    ON organizations(email_domain) WHERE email_domain IS NOT NULL;


-- ── Properties (buildings) ───────────────────────────────────────────────────
-- Physical properties (buildings) owned/managed by organizations
CREATE TABLE IF NOT EXISTS properties (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    name            VARCHAR(255) NOT NULL,
    address         TEXT,
    city            VARCHAR(100),
    province        VARCHAR(50),
    postal_code     VARCHAR(20),
    unit_count      INTEGER DEFAULT 0 NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ  -- soft delete
);

CREATE INDEX IF NOT EXISTS idx_properties_org ON properties(org_id);

-- ── Units ────────────────────────────────────────────────────────────────────
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
    deleted_at      TIMESTAMPTZ,  -- soft delete
    CONSTRAINT uq_units_property_unit_number UNIQUE(property_id, unit_number)
);

CREATE INDEX IF NOT EXISTS idx_units_property ON units(property_id);
CREATE INDEX IF NOT EXISTS idx_units_email ON units(tenant_email);

-- ── Incidents (unified operational thread) ───────────────────────────────────
CREATE TABLE IF NOT EXISTS incidents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    property_id     UUID REFERENCES properties(id) ON DELETE SET NULL,
    unit_id         UUID REFERENCES units(id) ON DELETE SET NULL,
    thread_id       UUID NOT NULL DEFAULT gen_random_uuid(),
    title           VARCHAR(500) NOT NULL,
    category        VARCHAR(100)
                    CHECK (category IS NULL OR category IN ('maintenance', 'billing', 'noise', 'lease', 'move_in', 'move_out', 'general')),
    urgency         VARCHAR(50) DEFAULT 'MEDIUM' NOT NULL
                    CHECK (urgency IN ('EMERGENCY', 'HIGH', 'MEDIUM', 'LOW')),
    status          VARCHAR(50) DEFAULT 'OPEN' NOT NULL
                    CHECK (status IN ('OPEN', 'PENDING_APPROVAL', 'DISPATCH_READY', 'DISPATCHED', 'IN_PROGRESS', 'RESOLVED', 'CLOSED')),
    ai_summary      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ  -- soft delete
);

CREATE INDEX IF NOT EXISTS idx_incidents_org_status ON incidents(org_id, status) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_incidents_thread ON incidents(thread_id);
CREATE INDEX IF NOT EXISTS idx_incidents_urgency ON incidents(urgency, status);
CREATE INDEX IF NOT EXISTS idx_incidents_created ON incidents(created_at DESC);

-- ── AI Drafts (proposed responses) ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ai_drafts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id     UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    org_id          UUID NOT NULL REFERENCES organizations(id),
    draft_type      VARCHAR(50) NOT NULL,  -- tenant_reply | vendor_outreach | owner_briefing
    subject         VARCHAR(255),
    body            TEXT NOT NULL,
    recipient_email VARCHAR(255),
    status          VARCHAR(50) DEFAULT 'pending',  -- pending | approved | rejected | sent | failed
    approved_by     VARCHAR(255),           -- User who approved (derived from auth)
    approved_at     TIMESTAMPTZ,
    rejected_by     VARCHAR(255),           -- User who rejected (derived from auth)
    rejected_at     TIMESTAMPTZ,
    rejection_reason TEXT,                  -- Why the draft was rejected
    sent_at         TIMESTAMPTZ,
    error_message   TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_drafts_incident ON ai_drafts(incident_id);
CREATE INDEX IF NOT EXISTS idx_ai_drafts_org_status ON ai_drafts(org_id, status);
CREATE INDEX IF NOT EXISTS idx_ai_drafts_created ON ai_drafts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_drafts_approved_at ON ai_drafts(approved_at) WHERE status = 'approved';

-- ── Communication Log (audit trail) ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS communication_logs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id          UUID NOT NULL REFERENCES organizations(id),
    incident_id     UUID REFERENCES incidents(id),
    draft_id        UUID REFERENCES ai_drafts(id),
    direction       VARCHAR(50) NOT NULL,  -- inbound | outbound
    channel         VARCHAR(50) NOT NULL,  -- email | sms | in_app
    sender          VARCHAR(255),
    recipient       VARCHAR(255),
    subject         VARCHAR(255),
    body            TEXT,
    status          VARCHAR(50),           -- sent | received | failed
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_comm_logs_incident ON communication_logs(incident_id);
CREATE INDEX IF NOT EXISTS idx_comm_logs_org ON communication_logs(org_id, created_at DESC);
---