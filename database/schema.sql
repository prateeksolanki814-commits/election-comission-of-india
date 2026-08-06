-- ============================================================================
-- DEMO / RESEARCH PROTOTYPE SCHEMA — NOT FOR REAL ELECTIONS
-- Synthetic data only.
--
-- Key architectural rule enforced here:
--   `eligibility` schema (who may vote) and `ballots` schema (what was voted)
--   are separate Postgres schemas with separate roles. There is NO foreign
--   key from anonymous_ballots to synthetic_voters. The only bridge is the
--   voting_credentials table, keyed by an opaque token hash with no voter_id
--   column at all.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS eligibility;
CREATE SCHEMA IF NOT EXISTS ballots;
CREATE SCHEMA IF NOT EXISTS audit;
CREATE SCHEMA IF NOT EXISTS metrics;

-- ----------------------------------------------------------------------------
-- Roles (least privilege). Passwords set via env at deploy time, not here.
-- ----------------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'role_eligibility_svc') THEN
    CREATE ROLE role_eligibility_svc LOGIN;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'role_ballot_svc') THEN
    CREATE ROLE role_ballot_svc LOGIN;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'role_admin_svc') THEN
    CREATE ROLE role_admin_svc LOGIN;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'role_analytics_svc') THEN
    CREATE ROLE role_analytics_svc LOGIN;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'role_auditor_svc') THEN
    CREATE ROLE role_auditor_svc LOGIN;
  END IF;
END$$;

-- ============================================================================
-- ELIGIBILITY SCHEMA — identity & OTP simulation, never touches ballot content
-- ============================================================================

CREATE TABLE IF NOT EXISTS eligibility.users_demo (
    user_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role            VARCHAR(20) NOT NULL CHECK (role IN ('admin','auditor','operator')),
    username        VARCHAR(64) NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,             -- bcrypt/argon2 hash only
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active       BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS eligibility.synthetic_voters (
    voter_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    synthetic_voter_code VARCHAR(20) NOT NULL UNIQUE,   -- e.g. "DEMO-VOTER-000123"
    constituency_id      UUID NOT NULL,
    otp_secret_hash       TEXT NOT NULL,                 -- simulated OTP secret, hashed
    language_pref         VARCHAR(8) NOT NULL DEFAULT 'en',
    accessibility_prefs    JSONB NOT NULL DEFAULT '{}'::jsonb,
    has_voted_flag         BOOLEAN NOT NULL DEFAULT false,  -- boolean ONLY, never the choice
    is_eligible            BOOLEAN NOT NULL DEFAULT true,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_constituency FOREIGN KEY (constituency_id)
        REFERENCES ballots.constituencies(constituency_id)
);

CREATE INDEX IF NOT EXISTS idx_voters_constituency ON eligibility.synthetic_voters(constituency_id);
CREATE INDEX IF NOT EXISTS idx_voters_has_voted ON eligibility.synthetic_voters(has_voted_flag);

CREATE TABLE IF NOT EXISTS eligibility.auth_attempts (
    attempt_id      BIGSERIAL PRIMARY KEY,
    voter_code_hash TEXT NOT NULL,      -- hashed, never plaintext voter code in logs
    ip_hash         TEXT NOT NULL,      -- hashed source IP
    success         BOOLEAN NOT NULL,
    reason          VARCHAR(64),        -- 'bad_otp' | 'rate_limited' | 'not_eligible' | 'ok'
    attempted_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_auth_attempts_time ON eligibility.auth_attempts(attempted_at);

-- Voting credentials: THE ONLY BRIDGE TABLE. No voter_id column by design.
CREATE TABLE IF NOT EXISTS eligibility.voting_credentials (
    token_hash      TEXT PRIMARY KEY,             -- SHA-256 of raw token; raw token never stored
    election_id     UUID NOT NULL,
    constituency_id UUID NOT NULL,
    status          VARCHAR(10) NOT NULL DEFAULT 'unused'
                        CHECK (status IN ('unused','used','expired')),
    issued_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL,
    used_at         TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_credentials_status ON eligibility.voting_credentials(status);
CREATE INDEX IF NOT EXISTS idx_credentials_election ON eligibility.voting_credentials(election_id);

-- ============================================================================
-- BALLOTS SCHEMA — election config, candidates, and anonymous ballots
-- ============================================================================

CREATE TABLE IF NOT EXISTS ballots.elections (
    election_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           VARCHAR(200) NOT NULL,
    status          VARCHAR(10) NOT NULL DEFAULT 'draft'
                        CHECK (status IN ('draft','open','closed')),
    opens_at        TIMESTAMPTZ,
    closes_at       TIMESTAMPTZ,
    created_by      UUID,                 -- references eligibility.users_demo, no FK across schema
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_demo         BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS ballots.constituencies (
    constituency_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    election_id     UUID NOT NULL REFERENCES ballots.elections(election_id),
    name            VARCHAR(120) NOT NULL,      -- fictional constituency name
    code            VARCHAR(20) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS ballots.fictional_candidates (
    candidate_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    election_id     UUID NOT NULL REFERENCES ballots.elections(election_id),
    constituency_id UUID NOT NULL REFERENCES ballots.constituencies(constituency_id),
    name            VARCHAR(120) NOT NULL,     -- fictional candidate name
    symbol          VARCHAR(60) NOT NULL,      -- fictional symbol e.g. "Lantern"
    manifesto_summary TEXT NOT NULL,
    display_order   INT NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_candidates_constituency ON ballots.fictional_candidates(constituency_id);

-- THE ANONYMOUS BALLOT TABLE — deliberately has NO voter_id / no FK to
-- eligibility.synthetic_voters. This is the architectural core of the demo.
CREATE TABLE IF NOT EXISTS ballots.anonymous_ballots (
    ballot_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    election_id     UUID NOT NULL REFERENCES ballots.elections(election_id),
    constituency_id UUID NOT NULL REFERENCES ballots.constituencies(constituency_id),
    candidate_id    UUID NOT NULL REFERENCES ballots.fictional_candidates(candidate_id),
    idempotency_key TEXT NOT NULL,
    reference_number VARCHAR(24) NOT NULL UNIQUE,   -- shown to voter as receipt
    cast_at         TIMESTAMPTZ NOT NULL DEFAULT now()
    -- NOTE: intentionally no voter_id, no token, no IP, no device fingerprint.
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ballot_idempotency
    ON ballots.anonymous_ballots(election_id, idempotency_key);
CREATE INDEX IF NOT EXISTS idx_ballots_election ON ballots.anonymous_ballots(election_id);
CREATE INDEX IF NOT EXISTS idx_ballots_candidate ON ballots.anonymous_ballots(candidate_id);
CREATE INDEX IF NOT EXISTS idx_ballots_cast_at ON ballots.anonymous_ballots(cast_at);

CREATE TABLE IF NOT EXISTS eligibility.admin_roles (
    user_id     UUID NOT NULL REFERENCES eligibility.users_demo(user_id),
    role        VARCHAR(20) NOT NULL CHECK (role IN ('admin','auditor','operator')),
    granted_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, role)
);

-- ============================================================================
-- AUDIT SCHEMA — append-only, hash-chained
-- ============================================================================

CREATE TABLE IF NOT EXISTS audit.audit_events (
    event_id        BIGSERIAL PRIMARY KEY,
    event_type      VARCHAR(64) NOT NULL,   -- e.g. 'election_opened','ballot_cast','token_reuse_blocked'
    actor_role       VARCHAR(20),            -- 'admin' | 'system' | 'voter' (never voter identity)
    election_id      UUID,
    payload_summary  JSONB NOT NULL DEFAULT '{}'::jsonb,  -- no voter identity, no candidate choice
    prev_hash        TEXT NOT NULL,
    event_hash        TEXT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_time ON audit.audit_events(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_type ON audit.audit_events(event_type);

-- Prevent UPDATE/DELETE on audit_events at the DB level (append-only enforcement)
CREATE OR REPLACE FUNCTION audit.reject_modification() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit.audit_events is append-only; % is not permitted', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_no_update ON audit.audit_events;
CREATE TRIGGER trg_audit_no_update
    BEFORE UPDATE OR DELETE ON audit.audit_events
    FOR EACH ROW EXECUTE FUNCTION audit.reject_modification();

-- ============================================================================
-- METRICS SCHEMA — for the analytics dashboard (aggregates only)
-- ============================================================================

CREATE TABLE IF NOT EXISTS metrics.system_metrics (
    metric_id       BIGSERIAL PRIMARY KEY,
    metric_name     VARCHAR(64) NOT NULL,   -- 'response_time_ms' | 'error_rate' | 'active_sessions'
    metric_value    DOUBLE PRECISION NOT NULL,
    tags            JSONB NOT NULL DEFAULT '{}'::jsonb,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_metrics_name_time ON metrics.system_metrics(metric_name, recorded_at);

-- Materialized view for participation dashboards — aggregate-only, refreshed
-- periodically by Celery beat, never queried live against raw ballots for
-- the public dashboard.
CREATE MATERIALIZED VIEW IF NOT EXISTS metrics.mv_participation_by_constituency AS
SELECT
    c.constituency_id,
    c.name AS constituency_name,
    c.election_id,
    COUNT(b.ballot_id) AS votes_cast
FROM ballots.constituencies c
LEFT JOIN ballots.anonymous_ballots b ON b.constituency_id = c.constituency_id
GROUP BY c.constituency_id, c.name, c.election_id;

-- ============================================================================
-- GRANTS — least privilege, this is what actually enforces the separation
-- ============================================================================

GRANT USAGE ON SCHEMA eligibility TO role_eligibility_svc, role_admin_svc, role_auditor_svc;
GRANT USAGE ON SCHEMA ballots TO role_ballot_svc, role_admin_svc, role_analytics_svc, role_auditor_svc;
GRANT USAGE ON SCHEMA audit TO role_eligibility_svc, role_ballot_svc, role_admin_svc, role_auditor_svc;
GRANT USAGE ON SCHEMA metrics TO role_analytics_svc, role_admin_svc;

-- Eligibility service: full access to its own schema, NO access to ballots content
GRANT SELECT, INSERT, UPDATE ON eligibility.synthetic_voters, eligibility.voting_credentials,
    eligibility.auth_attempts TO role_eligibility_svc;
GRANT INSERT ON audit.audit_events TO role_eligibility_svc;

-- Ballot service: full access to anonymous_ballots, NO access to synthetic_voters at all
GRANT SELECT, INSERT ON ballots.anonymous_ballots TO role_ballot_svc;
GRANT SELECT ON ballots.elections, ballots.constituencies, ballots.fictional_candidates TO role_ballot_svc;
GRANT SELECT, UPDATE ON eligibility.voting_credentials TO role_ballot_svc;  -- status flip only, no voter table access
GRANT INSERT ON audit.audit_events TO role_ballot_svc;
-- Explicitly NOT granting role_ballot_svc anything on eligibility.synthetic_voters.

-- Analytics: read-only aggregates
GRANT SELECT ON metrics.mv_participation_by_constituency, metrics.system_metrics TO role_analytics_svc;
GRANT SELECT ON ballots.elections, ballots.constituencies TO role_analytics_svc;
-- Analytics is NOT granted row-level SELECT on anonymous_ballots directly in production
-- mode; local demo grants it for dashboard convenience — see docs/PRIVACY.md.

-- Auditor: read-only on audit log + aggregate metrics, nothing else
GRANT SELECT ON audit.audit_events TO role_auditor_svc;
GRANT SELECT ON metrics.mv_participation_by_constituency TO role_auditor_svc;

-- Admin: election/candidate management, no ballot content, no individual voter choice
GRANT SELECT, INSERT, UPDATE ON ballots.elections, ballots.constituencies,
    ballots.fictional_candidates TO role_admin_svc;
GRANT SELECT ON eligibility.synthetic_voters TO role_admin_svc;  -- eligibility mgmt only, has_voted_flag visible, choice never stored anywhere
GRANT INSERT ON audit.audit_events TO role_admin_svc;
GRANT SELECT ON audit.audit_events TO role_admin_svc;
