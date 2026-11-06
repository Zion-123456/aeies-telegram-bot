import hashlib
import uuid

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from scripts.adopt_migrations import adopt, ROOT, PREFIX
from scripts.migrate import migrate
from scripts.verify_database import verify


@pytest.mark.parametrize(
    "drift", [None, "column", "seed", "policy", "history", "grant", "sequence"]
)
def test_verified_adoption_and_drift_refusal(world, drift):
    target_name = "aeies_adoption_" + uuid.uuid4().hex
    created = []
    with psycopg.connect(world.url, autocommit=True) as admin:
        try:
            for name in (target_name, "aeies_reference"):
                admin.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name))
                )
                created.append(name)
            target = make_conninfo(world.url, dbname=target_name)
            reference = make_conninfo(world.url, dbname="aeies_reference")
            with psycopg.connect(target) as c:
                for name in PREFIX:
                    c.execute((ROOT / name).read_text())
                c.execute("CREATE SCHEMA supabase_migrations")
                c.execute(
                    "CREATE TABLE supabase_migrations.schema_migrations(version text,name text)"
                )
                for i, name in enumerate(PREFIX):
                    c.execute(
                        "INSERT INTO supabase_migrations.schema_migrations VALUES (%s,%s)",
                        (str(i), name.removesuffix(".sql")),
                    )
                if drift == "column":
                    c.execute("ALTER TABLE aeies.resources ADD COLUMN unexpected text")
                elif drift == "seed":
                    c.execute("UPDATE aeies.departments SET name='Changed' WHERE id=1")
                elif drift == "policy":
                    c.execute("DROP POLICY backend_only ON aeies.resources")
                elif drift == "history":
                    c.execute("DELETE FROM supabase_migrations.schema_migrations")
                elif drift == "grant":
                    c.execute("GRANT USAGE ON SCHEMA aeies TO PUBLIC")
                elif drift == "sequence":
                    c.execute("ALTER SEQUENCE aeies.resources_id_seq INCREMENT BY 2")
            with pytest.raises(ValueError, match="adoption"):
                migrate(target)
            if drift:
                with pytest.raises(ValueError):
                    adopt(target, reference)
                with psycopg.connect(target) as c:
                    assert (
                        c.execute(
                            "SELECT to_regclass('public.aeies_migrations')"
                        ).fetchone()[0]
                        is None
                    )
            else:
                adopt(target, reference)
                adopt(
                    target, reference
                )  # Repeat safely; never re-execute application DDL.
                with psycopg.connect(target) as c:
                    journal = dict(
                        c.execute("SELECT name,sha256 FROM public.aeies_migrations")
                    )
                    assert journal == {
                        name: hashlib.sha256(
                            (ROOT / name).read_text().encode()
                        ).hexdigest()
                        for name in PREFIX
                    }
                migrate(target)
                verify(target)
            with psycopg.connect(reference) as c:
                assert (
                    c.execute("SELECT to_regnamespace('aeies')").fetchone()[0] is None
                )
        finally:
            for name in reversed(created):
                admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
