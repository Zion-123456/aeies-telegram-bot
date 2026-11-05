-- Private server role, deliberately unrelated to Supabase Auth identities.
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aeies_backend') THEN
  CREATE ROLE aeies_backend NOLOGIN;
 END IF;
END $$;
GRANT USAGE ON SCHEMA aeies TO aeies_backend;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA aeies TO aeies_backend;
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA aeies TO aeies_backend;
REVOKE UPDATE,DELETE ON aeies.audit_logs FROM aeies_backend;
DO $$ DECLARE t record; BEGIN
 FOR t IN SELECT tablename FROM pg_tables WHERE schemaname='aeies' LOOP
  EXECUTE format('CREATE POLICY backend_only ON aeies.%I TO aeies_backend USING (true) WITH CHECK (true)',t.tablename);
 END LOOP;
END $$;
