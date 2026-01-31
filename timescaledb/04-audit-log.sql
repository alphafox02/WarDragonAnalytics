-- WarDragon Analytics - Audit Log Table (Optional)
--
-- This creates the audit_log table for persistent audit storage.
-- Only needed if you enable AUDIT_TO_DATABASE=true in .env
--
-- Safe to run multiple times (uses IF NOT EXISTS)
-- Run via: ./scripts/apply-schema.sh or manually

-- =============================================================================
-- AUDIT LOG TABLE
-- =============================================================================

CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    action TEXT NOT NULL,
    result TEXT NOT NULL,
    username TEXT NOT NULL,
    resource TEXT,
    details JSONB DEFAULT '{}',
    client_ip TEXT,
    user_agent TEXT
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_log_username ON audit_log(username);
CREATE INDEX IF NOT EXISTS idx_audit_log_resource ON audit_log(resource) WHERE resource IS NOT NULL;

-- Composite index for filtered queries
CREATE INDEX IF NOT EXISTS idx_audit_log_action_time ON audit_log(action, timestamp DESC);

-- =============================================================================
-- RETENTION POLICY (Optional)
-- =============================================================================

-- Keep audit logs for 1 year by default
-- Uncomment the following if you want automatic cleanup:
-- Note: Requires TimescaleDB hypertable, which we don't use here for simplicity

-- For manual cleanup, you can run:
-- DELETE FROM audit_log WHERE timestamp < NOW() - INTERVAL '1 year';

-- =============================================================================
-- VERIFICATION
-- =============================================================================

\echo 'Audit log table created successfully.'
\echo 'To enable audit logging to database, set AUDIT_TO_DATABASE=true in .env'
