from __future__ import annotations

import logging
from collections.abc import Callable

from telegram import Update
from telegram.ext import ContextTypes

from src.i18n import I18nService

logger = logging.getLogger(__name__)


def build_error_handler(i18n: I18nService) -> Callable[[object, ContextTypes.DEFAULT_TYPE], object]:
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
            logger.exception(
                "unhandled_bot_error update_type=%s",
                type(update).__name__,
                exc_info=context.error,
            )

        if isinstance(update, Update) and update.effective_message:
            language_code = update.effective_user.language_code if update.effective_user else None
            locale = i18n.resolve_locale(language_code)
            await update.effective_message.reply_text(
                f"❌ {i18n.t('messages.unexpected_error', locale=locale)}"
            )

    return on_error
