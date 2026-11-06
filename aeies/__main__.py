"""Long-polling entry point. Run with python -m aeies on Windows or Linux."""

import asyncio
import logging

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from aeies.config import Settings
from aeies.database.queries import Database
from aeies.handlers.router import handle_update, error_handler
from aeies.services.academic_service import AcademicService
from aeies.services.storage_service import TelegramStorage


async def initialize(application):
    service = application.bot_data["service"]

    def check():
        with service.database.transaction() as c:
            role = c.execute(
                "SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user"
            ).fetchone()
            if role["rolsuper"] or role["rolbypassrls"]:
                raise ValueError(
                    "Use a dedicated non-privileged backend login for the bot."
                )
            c.execute("SELECT id FROM profiles LIMIT 1")

    await asyncio.to_thread(check)
    await application.bot.set_my_commands(
        [
            ("start", "Start or return to menu"),
            ("register", "Register or update profile"),
            ("menu", "Main menu"),
            ("browse", "Browse academic resources"),
            ("search", "Search resources"),
            ("bookmarks", "Saved resources"),
            ("recent", "Recent uploads"),
            ("request", "Request a resource"),
            ("feedback", "Submit feedback"),
            ("profile", "View profile"),
            ("help", "Help"),
            ("admin", "Administration"),
            ("cancel", "Cancel current workflow"),
        ]
    )


def build_application(
    settings: Settings, *, request=None, polling_request=None
) -> Application:
    builder = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .request(
            request
            or HTTPXRequest(
                connection_pool_size=8,
                connect_timeout=15,
                read_timeout=45,
                write_timeout=60,
            )
        )
        .concurrent_updates(False)
        .post_init(initialize)
    )
    if polling_request:
        builder = builder.get_updates_request(polling_request)
    app = builder.build()
    app.bot_data["service"] = AcademicService(
        Database(settings.database_url), settings.backup_directory
    )
    app.bot_data["storage"] = TelegramStorage(settings.backup_directory)
    for command in (
        "start",
        "register",
        "menu",
        "help",
        "cancel",
        "resume",
        "profile",
        "browse",
        "search",
        "recent",
        "bookmarks",
        "open",
        "save",
        "unsave",
        "request",
        "feedback",
        "report",
        "track",
        "admin",
        "upload",
        "edit",
        "archive",
        "restore",
        "course",
        "courses",
        "coursepage",
        "browsecourse",
        "manage",
        "roles",
        "reference",
        "catalog",
        "feedbackqueue",
        "submission",
        "status",
        "analytics",
        "audit",
        "page",
    ):
        app.add_handler(
            CommandHandler(command, handle_update, filters=filters.ChatType.PRIVATE)
        )
    app.add_handler(CallbackQueryHandler(handle_update))
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & (filters.TEXT | filters.Document.ALL),
            handle_update,
        )
    )
    app.add_error_handler(error_handler)
    return app


def main():
    try:
        settings = Settings.from_env()
        logging.basicConfig(
            level=settings.log_level,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        for name in ("httpx", "httpcore", "telegram", "psycopg"):
            logging.getLogger(name).setLevel(logging.CRITICAL)
        build_application(settings).run_polling(
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=False,
            bootstrap_retries=3,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    except Exception:
        raise SystemExit(
            "Startup failed. Check secure configuration, migrations, and network connectivity."
        ) from None


if __name__ == "__main__":
    main()
