"""Load runtime configuration without exposing credentials."""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str = field(repr=False)
    supabase_url: str = ""
    supabase_key: str = field(default="", repr=False)
    log_level: str = "INFO"
    database_url: str = field(default="", repr=False)
    backup_directory: str = "backups/originals"

    @classmethod
    def from_env(cls):
        load_dotenv()
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise ValueError("Set TELEGRAM_BOT_TOKEN in environment settings or .env")
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            raise ValueError("Set DATABASE_URL securely before starting the bot")
        return cls(
            token,
            os.getenv("SUPABASE_URL", ""),
            os.getenv("SUPABASE_KEY", ""),
            os.getenv("LOG_LEVEL", "INFO"),
            database_url,
            os.getenv("BACKUP_DIRECTORY", "backups/originals"),
        )
