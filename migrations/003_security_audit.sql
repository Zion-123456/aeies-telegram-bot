ALTER TABLE aeies.audit_logs ADD COLUMN details jsonb NOT NULL DEFAULT '{}'::jsonb;
-- Explicitly remove any grants inherited from Supabase project defaults.
DO $$ DECLARE r text; BEGIN
 FOREACH r IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
  IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
   EXECUTE format('REVOKE ALL ON SCHEMA aeies FROM %I',r);
   EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA aeies FROM %I',r);
   EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA aeies FROM %I',r);
   EXECUTE format('REVOKE ALL ON public.aeies_migrations FROM %I',r);
  END IF;
 END LOOP;
END $$;
