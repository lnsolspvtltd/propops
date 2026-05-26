-- PropOps Database Initialization Script
-- Executed by postgres:16-alpine container on /docker-entrypoint-initdb.d/
-- This is the same as schema.sql but can be customized per environment

\echo 'Creating PropOps schema...'
\set ON_ERROR_STOP on

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── Organizations ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS organizations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(255) NOT NULL,
    email_domain    VARCHAR(255),
    plan            VARCHAR(50) DEFAULT 'beta',
    unit_count      INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS properties (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    address         TEXT,
    city            VARCHAR(100),
    province        VARCHAR(50),
    postal_
