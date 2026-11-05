"""Public bot commands."""
from telegram import Update
from telegram.ext import ContextTypes

from aeies.services.assistant import help_message, welcome_message


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_message:
        await update.effective_message.reply_text(welcome_message())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_message:
        await update.effective_message.reply_text(help_message())
