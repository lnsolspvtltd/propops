-- PropOps PostgreSQL Schema Initialization
-- This file is automatically executed by Docker on first postgres container startup
-- Re-running is safe due to IF NOT EXISTS clauses

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

CREATE INDEX IF NOT EXISTS idx_organizations_email_domain ON organizations(email_domain);

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

CREATE INDEX IF NOT EXISTS idx_properties_org_id ON properties(org_id);

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

CREATE INDEX IF NOT EXISTS idx_units_property_id ON units(property_id);

-- ── Incidents (unified operational thread) ───────────────────────────────────
CREATE TABLE IF NOT EXISTS incidents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id          UUID NOT NULL REFERENCES organizations(id),
    property_id     UUID REFERENCES properties(id),
    unit_id         UUID REFERENCES units(id),
    thread_id       UUID NOT NULL DEFAULT uuid_generate_v4(),
    title           VARCHAR(500) NOT NULL,
    category        VARCHAR(100),
    urgency         VARCHAR(50),
    status          VARCHAR(50) DEFAULT 'OPEN',
    ai_summary      TEXT,
    ai_confidence   FLOAT,
    source_channel  VARCHAR(50),
    source_address  VARCHAR(255),
    raw_message     TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_incidents_org_status ON incidents(org_id, status) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_incidents_thread ON incidents(thread_id);
CREATE INDEX IF NOT EXISTS idx_incidents_urgency ON incidents(urgency, status);

-- ── Communication Logs ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS communication_logs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id     UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    thread_id       UUID NOT NULL,
    direction       VARCHAR(10) NOT NULL,
    channel         VARCHAR(50) NOT NULL,
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
    draft_type      VARCHAR(50),
    recipient_email VARCHAR(255),
    subject         VARCHAR(500),
    body            TEXT NOT NULL,
    ai_model        VARCHAR(100),
    confidence      FLOAT,
    status          VARCHAR(50) DEFAULT 'pending',
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
    actor           VARCHAR(255),
    details         JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_org_id ON audit_logs(org_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_incident_id ON audit_logs(incident_id);

-- ── Seed Data ────────────────────────────────────────────────────────────────
-- Insert a default test organization if none exists
INSERT INTO organizations (id, name, email_domain, plan, unit_count)
VALUES ('00000000-0000-0000-0000-000000000001', 'Test Organization', 'test.example.com', 'beta', 5)
ON CONFLICT DO NOTHING;

-- Insert a default test property if none exists
INSERT INTO properties (id, org_id, name, address, city, province, postal_code, unit_count)
VALUES (
    '00000000-0000-0000-0000-000000000002',
    '00000000-0000-0000-0000-000000000001',
    'Test Property',
    '123 Main St',
    'Toronto',
    'ON',
    'M5V 3A8',
    5
)
ON CONFLICT DO NOTHING;

GRANT CONNECT ON DATABASE propops TO postgres;
GRANT USAGE ON SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO postgres;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO postgres;
---