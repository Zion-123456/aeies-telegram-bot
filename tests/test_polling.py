"""Run PTB's real polling lifecycle twice against an entirely mocked Telegram API."""

import asyncio
import json

import pytest
from telegram.request import BaseRequest

from aeies.__main__ import build_application
from aeies.config import Settings


class TelegramAPI(BaseRequest):
    def __init__(self, update_id):
        self.update_id = update_id
        self.polled = asyncio.Event()
        self.replied = asyncio.Event()
        self.sent = False

    @property
    def read_timeout(self):
        return 1

    async def initialize(self):
        pass

    async def shutdown(self):
        pass

    async def do_request(self, url, method, request_data=None, **kwargs):
        endpoint = url.rsplit("/", 1)[-1]
        bot = {
            "id": 123456,
            "is_bot": True,
            "first_name": "AEIES",
            "username": "aeies_test_bot",
        }
        if endpoint == "getMe":
            result = bot
        elif endpoint == "getUpdates":
            self.polled.set()
            await asyncio.sleep(0.01)
            if not self.sent:
                self.sent = True
                result = [
                    {
                        "update_id": self.update_id,
                        "message": {
                            "message_id": 1,
                            "date": 1,
                            "chat": {"id": 100, "type": "private"},
                            "from": {"id": 100, "is_bot": False, "first_name": "Test"},
                            "text": "/start",
                            "entities": [
                                {"type": "bot_command", "offset": 0, "length": 6}
                            ],
                        },
                    }
                ]
            else:
                result = []
        elif endpoint == "sendMessage":
            self.replied.set()
            result = {
                "message_id": 10,
                "date": 1,
                "chat": {"id": 100, "type": "private"},
                "from": bot,
                "text": "Menu",
            }
        else:
            result = True
        return 200, json.dumps({"ok": True, "result": result}).encode()


@pytest.mark.asyncio
async def test_polling_start_stop_restart(world):
    for update_id in (999001, 999002):
        api = TelegramAPI(update_id)
        polling = TelegramAPI(update_id)
        app = build_application(
            Settings(
                "123456:mock-test-token",
                database_url=world.url,
                backup_directory=str(world.directory),
            ),
            request=api,
            polling_request=polling,
        )
        async with app:
            await app.post_init(app)
            await app.start()
            try:
                await app.updater.start_polling(poll_interval=0.01, bootstrap_retries=0)
                await asyncio.wait_for(polling.polled.wait(), 5)
                await asyncio.wait_for(api.replied.wait(), 5)
            finally:
                if app.updater.running:
                    await app.updater.stop()
                await app.stop()
