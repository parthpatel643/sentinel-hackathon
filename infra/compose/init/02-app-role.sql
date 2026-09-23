-- Sentinel Platform — the non-superuser role core_api's own queries run
-- as (see sentinel_core.config's `db_app_user`/`app_database_url` and
-- docs/08-SECURITY-HARDENING.md). Postgres RLS policies are always bypassed
-- by superusers and table owners, no exceptions — the `sentinel` role
-- (this database's owner, and a superuser in this dev image) stays on
-- migrations/DDL duty; `sentinel_app` is what actually has to respect the
-- department-tenancy RLS policies the migrations below define.
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sentinel_app') THEN
    CREATE ROLE sentinel_app WITH LOGIN PASSWORD 'sentinel-app-dev-password' NOSUPERUSER NOBYPASSRLS;
  END IF;
END
$$;

GRANT ALL PRIVILEGES ON DATABASE sentinel TO sentinel_app;
GRANT ALL ON SCHEMA public TO sentinel_app;
GRANT ALL ON ALL TABLES IN SCHEMA public TO sentinel_app;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO sentinel_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO sentinel_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO sentinel_app;
