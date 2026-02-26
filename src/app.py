from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from telegram.ext import Application

from src.bot.error_handler import build_error_handler
from src.bot.handlers import BotHandlers, register_handlers
from src.config.settings import load_settings
from src.core.context_store import SQLiteContextStore
from src.core.model_preferences_store import ModelPreferencesStore
from src.core.rate_limiter import SlidingWindowRateLimiter
from src.core.user_assets_store import UserAssetsStore
from src.i18n import I18nService
from src.services.ollama_client import OllamaClient
from src.utils.logging import configure_logging

logger = logging.getLogger(__name__)


def main() -> None:
    settings = load_settings()
    configure_logging(settings.log_level)

    try:
        app_version = version("ollama-telegram-bot")
    except PackageNotFoundError:
        app_version = "unknown"

    logger.info("Starting ollama-telegram-bot version=%s", app_version)

    application = Application.builder().token(settings.telegram_bot_token).build()

    locales_dir = Path(__file__).resolve().parent.parent / "locales"
    i18n = I18nService(locales_dir=locales_dir, default_locale=settings.bot_default_locale)
    i18n.validate_required_keys(BotHandlers.required_i18n_keys())

    logger.info(
        "startup_i18n default_locale=%s available_locales=%s locales_dir=%s",
        i18n.default_locale,
        ",".join(i18n.available_locales),
        locales_dir,
    )

    db_path = Path(settings.model_prefs_db_path)
    db_parent = db_path.parent
    logger.info(
        "startup_storage db_path=%s db_parent=%s db_parent_exists=%s",
        db_path,
        db_parent,
        db_parent.exists(),
    )

    logger.info(
        "startup_ollama base_url=%s cloud_base_url=%s default_model=%s use_chat_api=%s keep_alive=%s timeout_s=%d cloud_auth=%s",
        settings.ollama_base_url,
        settings.ollama_cloud_base_url,
        settings.ollama_default_model,
        settings.ollama_use_chat_api,
        settings.ollama_keep_alive,
        settings.request_timeout_seconds,
        settings.ollama_api_key is not None,
    )

    logger.info(
        "startup_runtime max_context_messages=%d image_max_bytes=%d document_max_bytes=%d document_max_chars=%d allowed_users=%d",
        settings.max_context_messages,
        settings.image_max_bytes,
        settings.document_max_bytes,
        settings.document_max_chars,
        len(settings.allowed_user_ids),
    )

    context_store = SQLiteContextStore(
        db_path=settings.model_prefs_db_path,
        max_turns=settings.max_context_messages,
    )
    model_preferences_store = ModelPreferencesStore(settings.model_prefs_db_path)
    user_assets_store = UserAssetsStore(settings.model_prefs_db_path)
    ollama_client = OllamaClient(
        base_url=settings.ollama_base_url,
        cloud_base_url=settings.ollama_cloud_base_url,
        timeout_seconds=settings.request_timeout_seconds,
        api_key=settings.ollama_api_key,
        auth_scheme=settings.ollama_auth_scheme,
    )

    handlers = BotHandlers(
        ollama_client=ollama_client,
        context_store=context_store,
        model_preferences_store=model_preferences_store,
        user_assets_store=user_assets_store,
        default_model=settings.ollama_default_model,
        use_chat_api=settings.ollama_use_chat_api,
        keep_alive=settings.ollama_keep_alive,
        image_max_bytes=settings.image_max_bytes,
        document_max_bytes=settings.document_max_bytes,
        document_max_chars=settings.document_max_chars,
        i18n=i18n,
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
    application.add_error_handler(build_error_handler(i18n))

    logger.info(
        "startup_rate_limit enabled=%s max_messages=%d window_seconds=%d",
        settings.rate_limit_max_messages > 0,
        settings.rate_limit_max_messages,
        settings.rate_limit_window_seconds,
    )

    logger.info("startup_ready entering_polling_loop")

    application.run_polling(
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
