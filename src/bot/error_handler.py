from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    if isinstance(update, Update):
        user_id = update.effective_user.id if update.effective_user else "unknown"
        chat_id = update.effective_chat.id if update.effective_chat else "unknown"
        logger.exception(
            "unhandled_bot_error user_id=%s chat_id=%s",
            user_id,
            chat_id,
            exc_info=context.error,
        )
    else:
        logger.exception("unhandled_bot_error update_type=%s", type(update).__name__, exc_info=context.error)

    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "❌ An unexpected error occurred. Please try again in a few seconds."
        )
