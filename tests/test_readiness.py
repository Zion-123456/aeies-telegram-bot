from unittest.mock import patch
import json
import os
import subprocess
import sys

import pytest

from aeies.database.queries import connect
from aeies.services.permission_service import Denied


def test_hostaddr_cannot_bypass_tls_requirement():
    with patch("aeies.database.queries.psycopg.connect") as connection:
        with pytest.raises(ValueError, match="verify-full"):
            connect("host=localhost hostaddr=192.0.2.1 dbname=example sslmode=disable")
        connection.assert_not_called()


def test_replayed_update_cannot_reveal_another_profile(world):
    first = world.send(100, "/profile", update_id=800001)
    assert json.dumps(world.send(100, "/profile", update_id=800001)) == json.dumps(
        first
    )
    with pytest.raises(Denied, match="cannot be replayed"):
        world.send(200, "/profile", update_id=800001)


def test_verifier_rejects_public_schema_access(world):
    from scripts.verify_database import verify

    with world.db.transaction() as c:
        c.execute("GRANT USAGE ON SCHEMA aeies TO PUBLIC")
    try:
        # anon may not exist outside the fresh-schema test; use an API-shaped role.
        import psycopg

        with psycopg.connect(world.url, autocommit=True) as c:
            exists = c.execute("SELECT 1 FROM pg_roles WHERE rolname='anon'").fetchone()
            if not exists:
                c.execute("CREATE ROLE anon NOLOGIN")
        try:
            with pytest.raises(ValueError, match="private-schema"):
                verify(world.url)
        finally:
            if not exists:
                with psycopg.connect(world.url, autocommit=True) as c:
                    c.execute("DROP ROLE anon")
    finally:
        with world.db.transaction() as c:
            c.execute("REVOKE USAGE ON SCHEMA aeies FROM PUBLIC")


def test_missing_database_configuration_is_safe(monkeypatch):
    from aeies.config import Settings

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:synthetic-placeholder")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with patch("aeies.config.load_dotenv"):
        with pytest.raises(ValueError, match="Set DATABASE_URL"):
            Settings.from_env()


@pytest.mark.asyncio
async def test_startup_rejects_migration_superuser(world):
    from aeies.__main__ import initialize
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    app = SimpleNamespace(
        bot_data={"service": world.service},
        bot=SimpleNamespace(set_my_commands=AsyncMock()),
    )
    with pytest.raises(ValueError, match="non-privileged"):
        await initialize(app)
    app.bot.set_my_commands.assert_not_called()


def test_migration_cli_never_uses_runtime_url():
    environment = dict(
        os.environ,
        DATABASE_URL="postgresql://127.0.0.1:1/unused",
        MIGRATION_DATABASE_URL="",
    )
    result = subprocess.run(
        [sys.executable, "scripts/migrate.py"],
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "Set MIGRATION_DATABASE_URL" in result.stderr
