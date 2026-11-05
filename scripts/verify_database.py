"""Read-only schema readiness verification; never outputs student data or credentials."""

import hashlib
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg
from dotenv import load_dotenv
from aeies.database.queries import connect

TABLES = {
    "departments",
    "academic_levels",
    "semesters",
    "academic_sessions",
    "courses",
    "resource_categories",
    "profiles",
    "admin_roles",
    "resources",
    "bookmarks",
    "resource_reports",
    "feedback",
    "audit_logs",
    "access_events",
    "conversations",
    "processed_updates",
}
INDEXES = {
    "admin_roles_profile",
    "courses_browse",
    "resources_browse",
    "resources_recent",
    "feedback_queue",
    "audit_recent",
    "access_resource",
}


def verify(url):
    with connect(url, connect_timeout=10) as c:
        c.execute("SET TRANSACTION READ ONLY")
        actual = dict(
            c.execute(
                "SELECT relname,relrowsecurity FROM pg_class p JOIN pg_namespace n ON n.oid=p.relnamespace WHERE n.nspname='aeies' AND p.relkind='r'"
            ).fetchall()
        )
        if set(actual) != TABLES or not all(actual.values()):
            raise ValueError("Required tables or RLS protections are missing.")
        indexes = {
            r[0]
            for r in c.execute(
                "SELECT indexname FROM pg_indexes WHERE schemaname='aeies'"
            )
        }
        if not INDEXES <= indexes:
            raise ValueError("Required query indexes are missing.")
        policies = c.execute(
            "SELECT tablename,roles FROM pg_policies WHERE schemaname='aeies'"
        ).fetchall()
        if {r[0] for r in policies} != TABLES or any(
            r[1] != ["aeies_backend"] for r in policies
        ):
            raise ValueError("Unexpected database access policies.")
        for path in sorted(
            (Path(__file__).resolve().parents[1] / "migrations").glob("*.sql")
        ):
            expected = hashlib.sha256(
                path.read_text(encoding="utf-8").encode()
            ).hexdigest()
            row = c.execute(
                "SELECT sha256 FROM public.aeies_migrations WHERE name=%s", (path.name,)
            ).fetchone()
            if not row or row[0] != expected:
                raise ValueError("Missing or modified migration: " + path.name)
        unique_tables = {
            r[0]
            for r in c.execute(
                "SELECT t.relname FROM pg_constraint con JOIN pg_class t ON t.oid=con.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='aeies' AND con.contype IN ('u','p')"
            )
        }
        if not TABLES <= unique_tables:
            raise ValueError("Required uniqueness constraints are missing.")
        if c.execute(
            "SELECT has_table_privilege('aeies_backend','aeies.audit_logs','UPDATE'),has_table_privilege('aeies_backend','aeies.audit_logs','DELETE')"
        ).fetchone() != (False, False):
            raise ValueError("Audit-log write protection is missing.")


if __name__ == "__main__":
    load_dotenv()
    url = os.getenv("MIGRATION_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not url:
        sys.exit("Set MIGRATION_DATABASE_URL securely for schema verification.")
    try:
        verify(url)
    except ValueError as exc:
        sys.exit(str(exc))
    except psycopg.Error:
        sys.exit(
            "Schema verification failed. Check database access; no changes were made."
        )
    print(
        "Verified required tables, RLS policies, indexes, unique constraints, audit permissions, and migration checksums."
    )
