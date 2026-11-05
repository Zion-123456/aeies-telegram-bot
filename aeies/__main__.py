"""Run with python -m aeies."""
import logging

from telegram.ext import Application, CommandHandler

from aeies.config import Settings
from aeies.handlers.general import help_command, start


def build_application(settings: Settings) -> Application:
    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    return app


def main():
    settings = Settings.from_env()
    logging.basicConfig(level=settings.log_level)
    # HTTP request URLs can contain the Telegram bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    build_application(settings).run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
