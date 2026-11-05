import os
import unittest
from unittest.mock import patch

from aeies.__main__ import build_application
from aeies.config import Settings
from aeies.database.client import create_database_client
from telegram.ext import CommandHandler


class ApplicationTests(unittest.IsolatedAsyncioTestCase):
    def test_application_registers_commands(self):
        app = build_application(Settings("123456:offline-test-placeholder"))
        commands = set().union(
            *(h.commands for h in app.handlers[0] if isinstance(h, CommandHandler))
        )
        self.assertTrue(
            {
                "start",
                "help",
                "register",
                "browse",
                "upload",
                "roles",
                "feedback",
            }.issubset(commands)
        )

    def test_missing_token(self):
        with patch.dict(os.environ, {}, clear=True), patch("aeies.config.load_dotenv"):
            with self.assertRaisesRegex(ValueError, "TELEGRAM_BOT_TOKEN"):
                Settings.from_env()

    def test_secrets_are_not_in_repr(self):
        settings = Settings("private-token", supabase_key="private-key")
        self.assertNotIn("private", repr(settings))

    def test_database_requires_configuration(self):
        with self.assertRaisesRegex(ValueError, "SUPABASE_URL"):
            create_database_client(Settings("placeholder"))
