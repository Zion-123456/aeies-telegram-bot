"""Adopt ONLY 001/002 after comparing against exact SQL in a disposable reference DB.

No application DDL or data is changed in the target. Any mismatch aborts adoption.
The reference database must be empty, local and named aeies_reference. Reference
DDL runs in a transaction that is always rolled back. Stop the bot and other DDL
writers during reconciliation. Credentials are read from secure configuration.
"""

import hashlib
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg
from psycopg.conninfo import conninfo_to_dict
from dotenv import load_dotenv
from aeies.database.queries import connect

ROOT = Path(__file__).resolve().parents[1] / "migrations"
PREFIX = ("001_initial.sql", "002_backend_role.sql")


def snapshot(c):
    c.execute("SET LOCAL search_path TO aeies,pg_catalog")
    queries = {
        "relations": "SELECT relname,relkind,relrowsecurity,relforcerowsecurity FROM pg_class WHERE relnamespace='aeies'::regnamespace ORDER BY relname",
        "columns": "SELECT t.relname,a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,a.attidentity,a.attgenerated,pg_get_expr(d.adbin,d.adrelid) FROM pg_attribute a JOIN pg_class t ON t.oid=a.attrelid LEFT JOIN pg_attrdef d ON d.adrelid=t.oid AND d.adnum=a.attnum WHERE t.relnamespace='aeies'::regnamespace AND a.attnum>0 AND NOT a.attisdropped ORDER BY t.relname,a.attnum",
        "constraints": "SELECT t.relname,c.conname,c.contype,pg_get_constraintdef(c.oid),c.convalidated,c.condeferrable,c.condeferred FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid WHERE t.relnamespace='aeies'::regnamespace ORDER BY t.relname,c.conname",
        "indexes": "SELECT indexname,indexdef FROM pg_indexes WHERE schemaname='aeies' ORDER BY indexname",
        "policies": "SELECT tablename,policyname,permissive,roles,cmd,qual,with_check FROM pg_policies WHERE schemaname='aeies' ORDER BY tablename,policyname",
        "triggers": "SELECT t.relname,pg_get_triggerdef(g.oid) FROM pg_trigger g JOIN pg_class t ON t.oid=g.tgrelid WHERE t.relnamespace='aeies'::regnamespace AND NOT g.tgisinternal ORDER BY t.relname,g.tgname",
        "routines": "SELECT proname,pg_get_functiondef(oid) FROM pg_proc WHERE pronamespace='aeies'::regnamespace ORDER BY proname,oid",
        "grants": "SELECT t.relname,CASE WHEN x.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(x.grantee) END,x.privilege_type,x.is_grantable FROM pg_class t CROSS JOIN LATERAL aclexplode(coalesce(t.relacl,acldefault(CASE WHEN t.relkind='S' THEN 'S'::\"char\" ELSE 'r'::\"char\" END,t.relowner))) x WHERE t.relnamespace='aeies'::regnamespace AND x.grantee<>t.relowner ORDER BY 1,2,3,4",
        "schema_grants": "SELECT CASE WHEN x.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(x.grantee) END,x.privilege_type,x.is_grantable FROM pg_namespace n CROSS JOIN LATERAL aclexplode(coalesce(n.nspacl,acldefault('n',n.nspowner))) x WHERE n.nspname='aeies' AND x.grantee<>n.nspowner ORDER BY 1,2,3",
        "defaults": "SELECT CASE WHEN defaclobjtype='r' THEN 'tables' ELSE defaclobjtype::text END,CASE WHEN x.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(x.grantee) END,x.privilege_type,x.is_grantable FROM pg_default_acl d CROSS JOIN LATERAL aclexplode(d.defaclacl) x WHERE d.defaclnamespace='aeies'::regnamespace AND x.grantee<>d.defaclrole ORDER BY 1,2,3,4",
        "backend": "SELECT rolcanlogin,rolsuper,rolbypassrls FROM pg_roles WHERE rolname='aeies_backend'",
        "backend_inheritance": "SELECT pg_get_userbyid(roleid),admin_option FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname='aeies_backend') ORDER BY 1,2",
        "sequence_definitions": "SELECT t.relname,s.seqtypid::regtype::text,s.seqstart,s.seqincrement,s.seqmax,s.seqmin,s.seqcache,s.seqcycle FROM pg_sequence s JOIN pg_class t ON t.oid=s.seqrelid WHERE t.relnamespace='aeies'::regnamespace ORDER BY t.relname",
        "column_grants": "SELECT t.relname,a.attname,CASE WHEN x.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(x.grantee) END,x.privilege_type,x.is_grantable FROM pg_attribute a JOIN pg_class t ON t.oid=a.attrelid CROSS JOIN LATERAL aclexplode(a.attacl) x WHERE t.relnamespace='aeies'::regnamespace AND x.grantee<>t.relowner ORDER BY 1,2,3,4,5",
    }
    result = {key: c.execute(query).fetchall() for key, query in queries.items()}
    for table in (
        "departments",
        "academic_levels",
        "semesters",
        "academic_sessions",
        "resource_categories",
    ):
        # These are public academic reference values, never student/application data.
        result["seed_" + table] = c.execute(
            f"SELECT * FROM {table} ORDER BY id"
        ).fetchall()
    return result


def adopt(target_url, reference_url):
    info = conninfo_to_dict(reference_url)
    if (
        info.get("dbname") != "aeies_reference"
        or info.get("host") not in ("localhost", "127.0.0.1")
        or info.get("hostaddr") not in (None, "127.0.0.1")
    ):
        raise ValueError("Reference must be an empty local aeies_reference database.")
    with connect(reference_url, connect_timeout=10) as ref:
        with ref.transaction(force_rollback=True):
            if ref.execute("SELECT to_regnamespace('aeies')").fetchone()[0]:
                raise ValueError("Reference database is not empty.")
            for name in PREFIX:
                ref.execute((ROOT / name).read_text(encoding="utf-8"))
            expected = snapshot(ref)
            with connect(target_url, connect_timeout=10) as target:
                target.execute("SELECT pg_advisory_xact_lock(887741001)")
                target.execute("SET LOCAL lock_timeout='10s'")
                owns_all = target.execute(
                    "SELECT n.nspowner=(SELECT oid FROM pg_roles WHERE rolname=current_user) AND NOT EXISTS(SELECT 1 FROM pg_class t WHERE t.relnamespace=n.oid AND t.relowner<>n.nspowner) FROM pg_namespace n WHERE n.nspname='aeies'"
                ).fetchone()
                if not owns_all or not owns_all[0]:
                    raise ValueError(
                        "Application ownership differs from the migration identity; inspect before adoption."
                    )
                # Lock existing application tables against concurrent DDL/data writes.
                target.execute(
                    "LOCK TABLE "
                    + ",".join(
                        "aeies." + r[0] for r in expected["relations"] if r[1] == "r"
                    )
                    + " IN SHARE MODE"
                )
                if not target.execute(
                    "SELECT to_regclass('supabase_migrations.schema_migrations')"
                ).fetchone()[0]:
                    raise ValueError(
                        "Supabase migration history is unavailable; no adoption performed."
                    )
                names = [name.removesuffix(".sql") for name in PREFIX]
                history = target.execute(
                    "SELECT name FROM supabase_migrations.schema_migrations WHERE name=ANY(%s)",
                    (names,),
                ).fetchall()
                if sorted(r[0] for r in history) != sorted(names):
                    raise ValueError(
                        "Supabase migration names differ or are duplicated; inspect before adoption."
                    )
                actual = snapshot(target)
                mismatches = [key for key in expected if expected[key] != actual[key]]
                if mismatches:
                    raise ValueError(
                        "Migration equivalence failed in: " + ", ".join(mismatches)
                    )
                target.execute(
                    "CREATE TABLE IF NOT EXISTS public.aeies_migrations(name text PRIMARY KEY,sha256 text NOT NULL,applied_at timestamptz DEFAULT now())"
                )
                target.execute("REVOKE ALL ON public.aeies_migrations FROM PUBLIC")
                for name in PREFIX:
                    digest = hashlib.sha256(
                        (ROOT / name).read_text(encoding="utf-8").encode()
                    ).hexdigest()
                    old = target.execute(
                        "SELECT sha256 FROM public.aeies_migrations WHERE name=%s",
                        (name,),
                    ).fetchone()
                    if old and old[0] != digest:
                        raise ValueError(
                            "Repository journal checksum mismatch; no adoption performed."
                        )
                    target.execute(
                        "INSERT INTO public.aeies_migrations(name,sha256) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                        (name, digest),
                    )


if __name__ == "__main__":
    load_dotenv()
    target = os.getenv("MIGRATION_DATABASE_URL")
    reference = os.getenv("ADOPTION_REFERENCE_DATABASE_URL")
    if not target or not reference:
        sys.exit(
            "Securely configure MIGRATION_DATABASE_URL and ADOPTION_REFERENCE_DATABASE_URL."
        )
    try:
        adopt(target, reference)
    except ValueError as exc:
        sys.exit(str(exc))
    except psycopg.Error:
        sys.exit(
            "Adoption failed; no changes committed. Inspect schema and migration history securely."
        )
    print(
        "Verified and adopted 001/002; application schema and Supabase history unchanged."
    )
