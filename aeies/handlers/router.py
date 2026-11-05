"""Telegram transport: no authorization decisions or direct SQL in handlers."""

import asyncio
import logging
from datetime import timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import RetryAfter, NetworkError, BadRequest, Forbidden

from aeies.database.queries import DatabaseUnavailable, Duplicate
from aeies.services.permission_service import Denied

logger = logging.getLogger(__name__)


async def retry_rate_limit(operation):
    for attempt in range(4):
        try:
            return await operation()
        except RetryAfter as exc:
            if attempt == 3:
                raise
            seconds = (
                exc.retry_after.total_seconds()
                if isinstance(exc.retry_after, timedelta)
                else exc.retry_after
            )
            await asyncio.sleep(seconds + 0.1)
    raise RuntimeError("Unreachable")


async def handle_update(update, context):
    message = update.effective_message
    user = update.effective_user
    if (
        not message
        or not user
        or not update.effective_chat
        or update.effective_chat.type != "private"
    ):
        return
    service = context.application.bot_data["service"]
    storage = context.application.bot_data["storage"]
    callback = update.callback_query
    if callback:
        try:
            await retry_rate_limit(lambda: callback.answer())
        except (BadRequest, NetworkError):
            pass
    text = callback.data if callback else (message.text or "")
    if not isinstance(text, str) or len(text) > 4096:
        return
    if text.startswith("input:"):
        text = text[6:]
    document = None
    try:
        if message.document and not callback:
            await asyncio.to_thread(service.upload_allowed, user.id)
            backup = await retry_rate_limit(
                lambda: storage.backup(context.bot, message.document)
            )
            d = message.document
            document = {
                "file_id": d.file_id,
                "file_unique_id": d.file_unique_id,
                "file_size": d.file_size,
                "mime_type": d.mime_type,
                "backup_path": backup.path,
                "backup_sha256": backup.sha256,
            }
        result = await asyncio.to_thread(
            service.handle, user.id, update.update_id, text, document
        )
        if result.get("delivery"):
            fresh = await asyncio.to_thread(
                service.delivery_resource, user.id, result["delivery"]["id"]
            )
            try:
                await retry_rate_limit(
                    lambda: storage.deliver(
                        context.bot, update.effective_chat.id, fresh
                    )
                )
                await asyncio.to_thread(
                    service.record_delivery, user.id, fresh["id"], update.update_id
                )
            except (BadRequest, Forbidden):
                await message.reply_text(
                    "Telegram could not deliver that file. Please /report "
                    + str(fresh["id"])
                    + ". An administrator can recover the retained original backup."
                )
                return
        buttons = result.get("buttons", [])
        keyboard = (
            InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton(label[:60], callback_data=data)]
                    for label, data in buttons
                ]
            )
            if buttons
            else None
        )
        await retry_rate_limit(
            lambda: message.reply_text(result["text"][:4000], reply_markup=keyboard)
        )
    except (ValueError, Denied, Duplicate) as exc:
        await message.reply_text(str(exc))
    except DatabaseUnavailable:
        logger.warning("event=database_unavailable")
        await message.reply_text(
            "The database is temporarily unavailable. Please retry your last action; no partial changes were saved."
        )
    except (NetworkError, RetryAfter):
        logger.warning("event=telegram_unavailable")
    except OSError:
        logger.warning("event=backup_io_failure")
        await message.reply_text(
            "The original file could not be backed up. Nothing was published. Please contact an administrator."
        )


async def error_handler(update, context):
    logger.error(
        "event=unhandled_update_error error_type=%s", type(context.error).__name__
    )
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "The operation could not complete. Please retry or use /cancel."
            )
        except Exception:
            pass
