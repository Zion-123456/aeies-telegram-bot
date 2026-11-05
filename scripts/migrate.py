"""Apply immutable, checksum-verified migrations. Never logs connection strings."""

import hashlib
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg
from dotenv import load_dotenv
from aeies.database.queries import connect


def migrate(url):
    with connect(url, connect_timeout=10) as connection:
        connection.execute("SELECT pg_advisory_xact_lock(887741001)")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS public.aeies_migrations "
            "(name text PRIMARY KEY, sha256 text NOT NULL, applied_at timestamptz DEFAULT now())"
        )
        connection.execute("REVOKE ALL ON public.aeies_migrations FROM PUBLIC")
        for path in sorted(
            (Path(__file__).resolve().parents[1] / "migrations").glob("*.sql")
        ):
            content = path.read_text(encoding="utf-8")
            digest = hashlib.sha256(content.encode()).hexdigest()
            old = connection.execute(
                "SELECT sha256 FROM public.aeies_migrations WHERE name=%s", (path.name,)
            ).fetchone()
            if old:
                if old[0] != digest:
                    raise ValueError("An applied migration was modified: " + path.name)
                continue
            connection.execute(content)
            connection.execute(
                "INSERT INTO public.aeies_migrations(name,sha256) VALUES (%s,%s)",
                (path.name, digest),
            )
            print("Applied", path.name)


if __name__ == "__main__":
    load_dotenv()
    url = os.getenv("MIGRATION_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not url:
        sys.exit("Set MIGRATION_DATABASE_URL securely before applying migrations.")
    try:
        migrate(url)
    except (psycopg.Error, ValueError):
        sys.exit(
            "Migration failed; no changes committed. Check database access and migration integrity."
        )
