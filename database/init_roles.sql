-- Runs before schema.sql in docker-entrypoint-initdb.d ordering (0- prefix).
-- Creates service roles with passwords. In local Docker Compose these come
-- from the same .env used by the app containers; for any non-local
-- deployment, generate these via a secrets manager instead of a checked-in
-- file.

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'role_eligibility_svc') THEN
    CREATE ROLE role_eligibility_svc LOGIN PASSWORD 'change_me_eligibility';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'role_ballot_svc') THEN
    CREATE ROLE role_ballot_svc LOGIN PASSWORD 'change_me_ballot';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'role_admin_svc') THEN
    CREATE ROLE role_admin_svc LOGIN PASSWORD 'change_me_admin';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'role_analytics_svc') THEN
    CREATE ROLE role_analytics_svc LOGIN PASSWORD 'change_me_analytics';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'role_auditor_svc') THEN
    CREATE ROLE role_auditor_svc LOGIN PASSWORD 'change_me_auditor';
  END IF;
END$$;

-- NOTE: replace these literal passwords before any use beyond a fully
-- local, throwaway Docker Compose environment. See SECURITY.md.
