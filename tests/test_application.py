import os
import unittest
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

from aeies.__main__ import build_application
from aeies.config import Settings
from aeies.database.client import create_database_client
from aeies.handlers.general import start, help_command


class ApplicationTests(unittest.IsolatedAsyncioTestCase):
    async def test_commands_reply(self):
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(effective_message=message)
        await start(update, None)
        self.assertIn("Welcome to AEIES", message.reply_text.call_args.args[0])
        await help_command(update, None)
        self.assertIn("/help", message.reply_text.call_args.args[0])

    async def test_non_message_update(self):
        await start(SimpleNamespace(effective_message=None), None)
        await help_command(SimpleNamespace(effective_message=None), None)

    def test_application_registers_commands(self):
        app = build_application(Settings("123456:offline-test-placeholder"))
        self.assertEqual({"start", "help"},
                         set().union(*(h.commands for h in app.handlers[0])))

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
