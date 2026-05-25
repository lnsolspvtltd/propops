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
    ON organizations(deleted_at) WHERE deleted_at IS NULL;
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
    ON units(deleted_at) WHERE deleted_at IS NULL;


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
    category        VARCHAR(100)
                    CHECK (category IS NULL OR category IN (
                        'maintenance', 'billing', 'noise', 'lease', 
                        'move_in', 'move_out', 'general'
                    )),
    urgency         VARCHAR(50) DEFAULT 'MEDIUM'
                    CHECK (urgency IN ('EMERGENCY', 'HIGH', 'MEDIUM', 'LOW')),
    status          VARCHAR(50) DEFAULT 'OPEN'
                    CHECK (status IN (
                        'OPEN', 'PENDING_APPROVAL', 'DISPATCH_READY', 'DISPATCHED',
                        'IN_PROGRESS', 'RESOLVED', 'CLOSED'
                    )),
    ai_summary      TEXT,
    ai_confidence   FLOAT CHECK (ai_confidence >= 0 AND ai_confidence <= 1),
    source_channel  VARCHAR(50)
                    CHECK (source_channel IN ('email', 'sms', 'portal', 'manual')),
    source_address  VARCHAR(255),
    raw_message     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ,
    deleted_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_incidents_org_status 
    ON incidents(org_id, status) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_incidents_thread 
    ON incidents(thread_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_incidents_urgency_status 
    ON incidents(urgency, status) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_incidents_property 
    ON incidents(property_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_incidents_deleted 
    ON incidents(deleted_at) WHERE deleted_at IS NULL;


-- ── Communication Logs (all inbound/outbound messages linked to incident) ────
CREATE TABLE IF NOT EXISTS communication_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id     UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    thread_id       UUID NOT NULL,
    direction       VARCHAR(10) NOT NULL
                    CHECK (direction IN ('inbound', 'outbound')),
    channel         VARCHAR(50) NOT NULL
                    CHECK (channel IN ('email', 'sms', 'portal')),
    sender          VARCHAR(255),
    recipient       VARCHAR(255),
    subject         VARCHAR(500),
    body            TEXT,
    raw_headers     JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_comm_logs_incident 
    ON communication_logs(incident_id);
CREATE INDEX IF NOT EXISTS idx_comm_logs_thread 
    ON communication_logs(thread_id);
CREATE INDEX IF NOT EXISTS idx_comm_logs_created 
    ON communication_logs(created_at DESC);


-- ── AI Drafts (generated drafts pending approval) ─────────────────────────
CREATE TABLE IF NOT EXISTS ai_drafts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_id     UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    draft_type      VARCHAR(50)
                    CHECK (draft_type IN ('tenant_reply', 'vendor_outreach', 'escalation')),
    recipient_email VARCHAR(255),
    subject         VARCHAR(500),
    body            TEXT NOT NULL,
    ai_model        VARCHAR(100),
    confidence      FLOAT CHECK (confidence >= 0 AND confidence <= 1),
    status          VARCHAR(50) DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'rejected', 'sent')),
    approved_by     VARCHAR(255),
    approved_at     TIMESTAMPTZ,
    sent_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_drafts_incident 
    ON ai_drafts(incident_id);
CREATE INDEX IF NOT EXISTS idx_drafts_status 
    ON ai_drafts(status) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_drafts_created 
    ON ai_drafts(created_at DESC);


-- ── Audit Log (every action with actor: ai or human) ────────────────────────
CREATE TABLE IF NOT EXISTS audit_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID REFERENCES organizations(id) ON DELETE SET NULL,
    incident_id     UUID REFERENCES incidents(id) ON DELETE SET NULL,
    action          VARCHAR(100) NOT NULL,
    actor           VARCHAR(255),
    details         JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_org 
    ON audit_logs(org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_incident 
    ON audit_logs(incident_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created 
    ON audit_logs(created_at DESC);

-- ────────────────────────────────────────────────────────────────────────────
-- End of Phase 1 Schema
```

---