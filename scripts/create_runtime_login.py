"""Create a dedicated login without placing the password in command arguments or logs."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg
from psycopg import sql
from dotenv import load_dotenv
from aeies.database.queries import connect


def create_login(url, password):
    if len(password) < 24:
        raise ValueError(
            "Use a generated runtime password with at least 24 characters."
        )
    with connect(url, connect_timeout=10) as c:
        if c.execute("SELECT 1 FROM pg_roles WHERE rolname='aeies_runtime'").fetchone():
            raise ValueError(
                "aeies_runtime already exists. No password or privileges were changed."
            )
        c.execute(
            sql.SQL(
                "CREATE ROLE aeies_runtime LOGIN PASSWORD {} IN ROLE aeies_backend"
            ).format(sql.Literal(password))
        )


if __name__ == "__main__":
    load_dotenv()
    url = os.getenv("MIGRATION_DATABASE_URL")
    password = os.getenv("DATABASE_RUNTIME_PASSWORD", "")
    if not url:
        sys.exit("Set MIGRATION_DATABASE_URL securely.")
    try:
        create_login(url, password)
    except ValueError as exc:
        sys.exit(str(exc))
    except psycopg.Error:
        sys.exit("Runtime login creation failed. Check database access and migrations.")
    print(
        "Dedicated runtime login created. Configure DATABASE_URL securely, then remove DATABASE_RUNTIME_PASSWORD."
    )
