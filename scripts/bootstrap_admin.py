"""One-time bootstrap. Subsequent role changes happen in Telegram and are audited."""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
import psycopg
from aeies.database.queries import connect


def bootstrap(url, telegram_id):
    if telegram_id <= 0:
        raise ValueError("Telegram ID must be positive.")
    with connect(url, connect_timeout=10) as c:
        c.execute("SET search_path TO aeies,pg_catalog")
        c.execute("SELECT pg_advisory_xact_lock(887741002)")
        if c.execute(
            "SELECT 1 FROM admin_roles WHERE role='super' AND active LIMIT 1"
        ).fetchone():
            raise ValueError(
                "A super administrator already exists. Use /roles in Telegram."
            )
        if not c.execute(
            "SELECT 1 FROM profiles WHERE id=%s AND full_name IS NOT NULL",
            (telegram_id,),
        ).fetchone():
            raise ValueError(
                "Complete Telegram registration before bootstrapping this ID."
            )
        role = c.execute(
            "INSERT INTO admin_roles(profile_id,role) VALUES (%s,'super') RETURNING id",
            (telegram_id,),
        ).fetchone()[0]
        c.execute(
            "INSERT INTO audit_logs(actor_id,action,entity,entity_id) VALUES (%s,'bootstrap_super','admin_roles',%s)",
            (telegram_id, role),
        )


if __name__ == "__main__":
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--telegram-id", required=True, type=int)
    args = parser.parse_args()
    url = os.getenv("MIGRATION_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not url:
        sys.exit("Set MIGRATION_DATABASE_URL securely.")
    try:
        bootstrap(url, args.telegram_id)
    except ValueError as exc:
        sys.exit(str(exc))
    except psycopg.Error:
        sys.exit("Bootstrap failed. Check database connectivity and migrations.")
    print("First super administrator created. Manage subsequent roles using /roles.")
