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

    @classmethod
    def from_env(cls):
        load_dotenv()
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise ValueError("Set TELEGRAM_BOT_TOKEN in environment settings or .env")
        return cls(token, os.getenv("SUPABASE_URL", ""),
                   os.getenv("SUPABASE_KEY", ""), os.getenv("LOG_LEVEL", "INFO"))
