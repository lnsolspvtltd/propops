-- PropOps PostgreSQL Schema
-- Phase 1: Inbox Triage Wedge

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── Organizations (PM companies) ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS organizations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(255) NOT NULL,
    email_domain    VARCHAR(255),
    plan            VARCHAR(50) DEFAULT 'beta',     -- beta | starter | pro
    unit_count      INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── Properties ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS properties (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    address         TEXT,
    city            VARCHAR(100),
    province        VARCHAR(50),
    postal_code     VARCHAR(20),
    unit_count      INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_properties_org ON properties(org_id);

-- ── Units ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS units (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    property_id     UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    unit_number     VARCHAR(50) NOT NULL,
    tenant_name     VARCHAR(255),
    tenant_email    VARCHAR(255),
    tenant_phone    VARCHAR(50),
    lease_start     DATE,
    lease_end       DATE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_units_property ON units(property_id);
CREATE INDEX IF NOT EXISTS idx_units_email ON units(tenant_email);

-- ── Incidents (unified operational thread) ───────────────────────────────────
CREATE TABLE IF NOT EXISTS incidents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id          UUID NOT NULL REFERENCES organizations(id),
    property_id     UUID REFERENCES properties(id),
    unit_id         UUID REFERENCES units(id),
    thread_id       UUID NOT NULL DEFAULT uuid_generate_v4(),  -- UOTL thread
    title           VARCHAR(500) NOT NULL,
    category        VARCHAR(100),   -- maintenance | billing | noise | lease | other
    urgency         VARCHAR(50),    -- EMERGENCY | HIGH | MEDIUM | LOW
    status          VARCHAR(50) DEFAULT 'OPEN',
    -- OPEN | PENDING_APPROVAL | DISPATCH_READY | DISPATCHED | IN_PROGRESS | RESOLVED | CLOSED
    ai_summary      TEXT,
    ai_confidence   FLOAT,
    source_channel  VARCHAR(50),    -- email | sms | portal
    source_address  VARCHAR(255),   -- sender email/phone
    raw_message     TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ
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