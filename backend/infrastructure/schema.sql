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

CREATE INDEX IF NOT EXISTS idx_incidents_org_status ON incidents(org_id, status);
CREATE INDEX IF NOT EXISTS idx_incidents_thread ON incidents(thread_id);
CREATE INDEX IF NOT EXISTS idx_incidents_urgency ON incidents(urgency, status);

-- ── Communication Logs ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS communication_logs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id     UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    thread_id       UUID NOT NULL,
    direction       VARCHAR(10) NOT NULL,   -- inbound | outbound
    channel         VARCHAR(50) NOT NULL,   -- email | sms | portal
    sender          VARCHAR(255),
    recipient       VARCHAR(255),
    subject         VARCHAR(500),
    body            TEXT,
    raw_headers     JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_comm_logs_incident ON communication_logs(incident_id);
CREATE INDEX IF NOT EXISTS idx_comm_logs_thread ON communication_logs(thread_id);

-- ── AI Drafts (approval queue) ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ai_drafts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id     UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    draft_type      VARCHAR(50),    -- tenant_reply | vendor_outreach | escalation
    recipient_email VARCHAR(255),
    subject         VARCHAR(500),
    body            TEXT NOT NULL,
    ai_model        VARCHAR(100),
    confidence      FLOAT,
    status          VARCHAR(50) DEFAULT 'pending',  -- pending | approved | rejected | sent
    approved_by     VARCHAR(255),
    approved_at     TIMESTAMPTZ,
    sent_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_drafts_incident ON ai_drafts(incident_id);
CREATE INDEX IF NOT EXISTS idx_drafts_status ON ai_drafts(status);

-- ── Audit Log ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_logs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id          UUID REFERENCES organizations(id),
    incident_id     UUID REFERENCES incidents(id),
    action          VARCHAR(100) NOT NULL,
    actor           VARCHAR(255),   -- 'ai:triage' | 'human:user@email.com'
    details         JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
