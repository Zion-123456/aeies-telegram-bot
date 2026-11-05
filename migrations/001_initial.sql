-- Applied once by scripts/migrate.py, in a single transaction.
CREATE SCHEMA aeies;
REVOKE ALL ON SCHEMA aeies FROM PUBLIC;
SET search_path TO aeies, pg_catalog;

CREATE TABLE departments (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 code text UNIQUE NOT NULL CHECK(length(code) BETWEEN 2 AND 20),
 name text NOT NULL CHECK(length(name) BETWEEN 2 AND 150),
 archived boolean NOT NULL DEFAULT false
);
CREATE TABLE academic_levels (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 name text UNIQUE NOT NULL CHECK(name ~ '^[1-6]00L$'), archived boolean NOT NULL DEFAULT false
);
CREATE TABLE semesters (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 name text UNIQUE NOT NULL CHECK(length(name) BETWEEN 2 AND 40), archived boolean NOT NULL DEFAULT false
);
CREATE TABLE academic_sessions (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 name text UNIQUE NOT NULL CHECK(name ~ '^[0-9]{4}/[0-9]{4}$'), archived boolean NOT NULL DEFAULT false
);
CREATE TABLE resource_categories (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 name text UNIQUE NOT NULL CHECK(length(name) BETWEEN 2 AND 80), archived boolean NOT NULL DEFAULT false
);
CREATE TABLE profiles (
 id bigint PRIMARY KEY CHECK(id > 0),
 full_name text CHECK(length(full_name) BETWEEN 2 AND 120),
 department_id bigint REFERENCES departments,
 level_id bigint REFERENCES academic_levels,
 semester_id bigint REFERENCES semesters,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 CHECK((full_name IS NULL AND department_id IS NULL AND level_id IS NULL)
    OR (full_name IS NOT NULL AND department_id IS NOT NULL AND level_id IS NOT NULL))
);
CREATE TABLE admin_roles (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 profile_id bigint NOT NULL REFERENCES profiles,
 role text NOT NULL CHECK(role IN ('super','executive','resource_admin')),
 department_id bigint REFERENCES departments, level_id bigint REFERENCES academic_levels,
 permissions text[] NOT NULL DEFAULT ARRAY['resources','feedback'],
 active boolean NOT NULL DEFAULT true,
 created_at timestamptz NOT NULL DEFAULT now(),
 CHECK(role <> 'resource_admin' OR (department_id IS NOT NULL AND level_id IS NOT NULL)),
 CHECK(permissions <@ ARRAY['resources','feedback','courses','analytics','audit','reference','roles']::text[])
);
CREATE INDEX admin_roles_profile ON admin_roles(profile_id) WHERE active;
CREATE TABLE courses (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 code text NOT NULL CHECK(code ~ '^[A-Z]{2,8}[0-9]{3,4}$'),
 title text NOT NULL CHECK(length(title) BETWEEN 2 AND 200),
 department_id bigint NOT NULL REFERENCES departments, level_id bigint NOT NULL REFERENCES academic_levels,
 semester_id bigint NOT NULL REFERENCES semesters, archived boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(code, department_id, level_id, semester_id)
);
CREATE INDEX courses_browse ON courses(department_id,level_id,semester_id) WHERE NOT archived;
CREATE TABLE resources (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 course_id bigint NOT NULL REFERENCES courses, category_id bigint NOT NULL REFERENCES resource_categories,
 session_id bigint NOT NULL REFERENCES academic_sessions,
 title text NOT NULL CHECK(length(title) BETWEEN 2 AND 200), description text NOT NULL DEFAULT '' CHECK(length(description)<=2000),
 file_id text NOT NULL, file_unique_id text UNIQUE NOT NULL,
 file_size bigint NOT NULL CHECK(file_size BETWEEN 1 AND 20971520),
 mime_type text NOT NULL CHECK(mime_type IN ('application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document')),
 backup_path text NOT NULL, backup_sha256 text NOT NULL CHECK(backup_sha256 ~ '^[a-f0-9]{64}$'),
 uploaded_by bigint NOT NULL REFERENCES profiles, uploaded_at timestamptz NOT NULL DEFAULT now(),
 status text NOT NULL DEFAULT 'published' CHECK(status IN ('published','archived')),
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX resources_browse ON resources(course_id, category_id, uploaded_at DESC) WHERE status='published';
CREATE INDEX resources_recent ON resources(uploaded_at DESC);
CREATE TABLE bookmarks (
 profile_id bigint NOT NULL REFERENCES profiles, resource_id bigint NOT NULL REFERENCES resources,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(profile_id,resource_id)
);
CREATE TABLE feedback (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 reference text UNIQUE NOT NULL DEFAULT ('AEIES-' || upper(replace(gen_random_uuid()::text,'-',''))),
 profile_id bigint NOT NULL REFERENCES profiles,
 department_id bigint NOT NULL REFERENCES departments, level_id bigint NOT NULL REFERENCES academic_levels,
 kind text NOT NULL CHECK(kind IN ('Missing resource','Incorrect resource','Broken resource','Outdated material','Incorrect course information','Suggestion','General feedback')),
 body text NOT NULL CHECK(length(body) BETWEEN 3 AND 2000),
 status text NOT NULL DEFAULT 'New' CHECK(status IN ('New','Under Review','Resolved','Declined')),
 assigned_to bigint REFERENCES profiles,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX feedback_queue ON feedback(department_id,level_id,status,created_at DESC);
CREATE TABLE resource_reports (
 feedback_id bigint PRIMARY KEY REFERENCES feedback,
 resource_id bigint NOT NULL REFERENCES resources
);
CREATE TABLE audit_logs (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 actor_id bigint NOT NULL REFERENCES profiles, action text NOT NULL,
 entity text NOT NULL, entity_id bigint NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_recent ON audit_logs(created_at DESC);
CREATE TABLE access_events (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 profile_id bigint NOT NULL REFERENCES profiles, resource_id bigint NOT NULL REFERENCES resources,
 update_id bigint NOT NULL UNIQUE, delivered_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX access_resource ON access_events(resource_id);
CREATE TABLE conversations (
 profile_id bigint PRIMARY KEY REFERENCES profiles,
 state jsonb NOT NULL DEFAULT '{}'::jsonb,
 updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE processed_updates (
 update_id bigint PRIMARY KEY, response jsonb NOT NULL, processed_at timestamptz NOT NULL DEFAULT now()
);

-- No anon/authenticated policies: Telegram users do not have Supabase Auth identities.
-- Only a trusted backend database connection may use this private schema.
DO $$ DECLARE t record; BEGIN
 FOR t IN SELECT tablename FROM pg_tables WHERE schemaname='aeies' LOOP
  EXECUTE format('ALTER TABLE aeies.%I ENABLE ROW LEVEL SECURITY',t.tablename);
  EXECUTE format('REVOKE ALL ON aeies.%I FROM PUBLIC',t.tablename);
 END LOOP;
END $$;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA aeies FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA aeies REVOKE ALL ON TABLES FROM PUBLIC;

INSERT INTO departments(code,name) VALUES
 ('EEE','Electrical & Electronics Engineering'),('ICE','Information & Communication Engineering'),('CPE','Computer Engineering');
INSERT INTO academic_levels(name) VALUES ('100L'),('200L'),('300L'),('400L'),('500L');
INSERT INTO semesters(name) VALUES ('Alpha'),('Omega');
INSERT INTO resource_categories(name) VALUES ('Lecture notes'),('Past questions and past sets'),('Textbooks'),('Educational videos'),('Course advice');
-- Academic sessions and real courses must be entered by an authorized administrator;
-- deliberately do not invent the university's course catalogue.
