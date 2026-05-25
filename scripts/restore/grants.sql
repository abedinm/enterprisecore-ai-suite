-- grants.sql — application role grants applied after a pg_restore.
--
-- pg_dump --no-owner --no-privileges produces a portable dump.
-- This file restores the application-tier permissions that depend on
-- environment-specific role names.
--
-- Edit the role names below to match your environment.

\set ec_app_role 'ec_app'
\set ec_ro_role  'ec_readonly'

-- Roles must already exist. Create them if not present.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ec_app') THEN
    CREATE ROLE ec_app LOGIN PASSWORD 'CHANGE_ME';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ec_readonly') THEN
    CREATE ROLE ec_readonly LOGIN PASSWORD 'CHANGE_ME';
  END IF;
END
$$;

-- Application role: full CRUD on every table in public.
GRANT CONNECT ON DATABASE :"DBNAME" TO ec_app;
GRANT USAGE ON SCHEMA public TO ec_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ec_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ec_app;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO ec_app;

-- Future tables created by migrations should automatically grant to the app role.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ec_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO ec_app;

-- Read-only role: SELECT everywhere. Used by analytics, dashboards.
GRANT CONNECT ON DATABASE :"DBNAME" TO ec_readonly;
GRANT USAGE ON SCHEMA public TO ec_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ec_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON TABLES TO ec_readonly;

-- Refresh planner statistics after restore.
ANALYZE;
