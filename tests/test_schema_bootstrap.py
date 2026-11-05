"""Verify a fresh migration with Supabase-style public API roles and default grants."""

import uuid
import secrets

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from scripts.migrate import migrate
from scripts.verify_database import verify
from scripts.create_runtime_login import create_login
from aeies.database.queries import Database
from aeies.services.academic_service import AcademicService


def test_fresh_database_and_public_api_roles(world):
    name = "aeies_schema_" + uuid.uuid4().hex
    created_roles = []
    created_database = False
    # world already validates that this cluster is a loopback aeies_test instance.
    with psycopg.connect(world.url, autocommit=True) as admin:
        try:
            for role in ("anon", "authenticated", "service_role"):
                if not admin.execute(
                    "SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)
                ).fetchone():
                    admin.execute(
                        sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role))
                    )
                    created_roles.append(role)
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
            created_database = True
            fresh = make_conninfo(world.url, dbname=name)
            with psycopg.connect(fresh) as c:
                c.execute(
                    "ALTER DEFAULT PRIVILEGES GRANT ALL ON TABLES TO anon,authenticated,service_role"
                )
            migrate(fresh)
            verify(fresh)
            create_login(fresh, secrets.token_urlsafe(32))
            created_roles.append("aeies_runtime")
            runtime = AcademicService(
                Database(make_conninfo(fresh, user="aeies_runtime")), world.directory
            )
            for update_id, text in enumerate(
                ("/register", "Runtime Student", "1", "3", "1"), start=1
            ):
                runtime.handle(701, update_id, text)
            assert "Runtime Student" in runtime.handle(701, 6, "/profile")["text"]
            with psycopg.connect(fresh) as c:
                assert c.execute(
                    "SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname='aeies_runtime'"
                ).fetchone() == (False, False)
                for role in ("anon", "authenticated", "service_role"):
                    assert c.execute(
                        "SELECT has_schema_privilege(%s,'aeies','USAGE')", (role,)
                    ).fetchone() == (False,)
                    assert c.execute(
                        "SELECT has_table_privilege(%s,'aeies.profiles','SELECT')",
                        (role,),
                    ).fetchone() == (False,)
                    assert c.execute(
                        "SELECT has_table_privilege(%s,'public.aeies_migrations','SELECT')",
                        (role,),
                    ).fetchone() == (False,)
        finally:
            if created_database:
                admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
            for role in created_roles:
                admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
