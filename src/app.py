from __future__ import annotations

import logging

from telegram.ext import Application

from src.bot.error_handler import on_error
from src.bot.handlers import BotHandlers, register_handlers
from src.config.settings import load_settings
from src.core.context_store import SQLiteContextStore
from src.core.model_preferences_store import ModelPreferencesStore
from src.core.rate_limiter import SlidingWindowRateLimiter
from src.services.ollama_client import OllamaClient
from src.utils.logging import configure_logging

logger = logging.getLogger(__name__)


def main() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)

    logger.info("Starting ollama-telegram-bot")

    application = Application.builder().token(settings.telegram_bot_token).build()

    context_store = SQLiteContextStore(
        db_path=settings.model_prefs_db_path,
        max_turns=settings.max_context_messages,
    )
    model_preferences_store = ModelPreferencesStore(settings.model_prefs_db_path)
    ollama_client = OllamaClient(
        base_url=settings.ollama_base_url,
        timeout_seconds=settings.request_timeout_seconds,
    )

    handlers = BotHandlers(
        ollama_client=ollama_client,
        context_store=context_store,
        model_preferences_store=model_preferences_store,
        default_model=settings.ollama_default_model,
        use_chat_api=settings.ollama_use_chat_api,
        keep_alive=settings.ollama_keep_alive,
        image_max_bytes=settings.image_max_bytes,
        allowed_user_ids=set(settings.allowed_user_ids),
        rate_limiter=(
            SlidingWindowRateLimiter(
                max_requests=settings.rate_limit_max_messages,
                window_seconds=settings.rate_limit_window_seconds,
            )
            if settings.rate_limit_max_messages > 0
            else None
        ),
    )

    register_handlers(application, handlers)
    application.add_error_handler(on_error)

    application.run_polling(
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
