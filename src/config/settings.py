from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    ollama_base_url: str
    ollama_api_key: str | None
    ollama_auth_scheme: str
    ollama_default_model: str
    ollama_use_chat_api: bool
    ollama_keep_alive: str
    model_prefs_db_path: str
    allowed_user_ids: tuple[int, ...]
    request_timeout_seconds: int
    max_context_messages: int
    rate_limit_max_messages: int
    rate_limit_window_seconds: int
    image_max_bytes: int
    document_max_bytes: int
    document_max_chars: int
    bot_default_locale: str
    log_level: str


def _parse_allowed_user_ids(raw: str) -> tuple[int, ...]:
    if not raw.strip():
        raise ValueError("ALLOWED_USER_IDS is required and cannot be empty")

    user_ids: list[int] = []
    for value in raw.split(","):
        token = value.strip()
        if not token:
            continue
        try:
            user_ids.append(int(token))
        except ValueError as error:
            raise ValueError("ALLOWED_USER_IDS must contain comma-separated numeric user IDs") from error

    parsed = tuple(dict.fromkeys(user_ids))
    if not parsed:
        raise ValueError("ALLOWED_USER_IDS is required and cannot be empty")

    return parsed


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError("OLLAMA_USE_CHAT_API must be a boolean value")


def load_settings() -> Settings:
    timeout_raw = os.getenv("REQUEST_TIMEOUT_SECONDS", "60").strip()
    max_context_raw = os.getenv("MAX_CONTEXT_MESSAGES", "12").strip()
    rate_limit_max_raw = os.getenv("RATE_LIMIT_MAX_MESSAGES", "0").strip()
    rate_limit_window_raw = os.getenv("RATE_LIMIT_WINDOW_SECONDS", "30").strip()
    image_max_bytes_raw = os.getenv("IMAGE_MAX_BYTES", "5242880").strip()
    document_max_bytes_raw = os.getenv("DOCUMENT_MAX_BYTES", "10485760").strip()
    document_max_chars_raw = os.getenv("DOCUMENT_MAX_CHARS", "12000").strip()
    use_chat_api_raw = os.getenv("OLLAMA_USE_CHAT_API", "true")
    ollama_keep_alive = os.getenv("OLLAMA_KEEP_ALIVE", "5m").strip()
    bot_default_locale = os.getenv("BOT_DEFAULT_LOCALE", "en").strip().lower()
    ollama_api_key = os.getenv("OLLAMA_API_KEY", "").strip() or None
    ollama_auth_scheme = os.getenv("OLLAMA_AUTH_SCHEME", "Bearer").strip()

    try:
        request_timeout_seconds = int(timeout_raw)
        max_context_messages = int(max_context_raw)
        rate_limit_max_messages = int(rate_limit_max_raw)
        rate_limit_window_seconds = int(rate_limit_window_raw)
        image_max_bytes = int(image_max_bytes_raw)
        document_max_bytes = int(document_max_bytes_raw)
        document_max_chars = int(document_max_chars_raw)
        ollama_use_chat_api = _parse_bool(use_chat_api_raw)
    except ValueError as error:
        raise ValueError(
            "REQUEST_TIMEOUT_SECONDS, MAX_CONTEXT_MESSAGES, RATE_LIMIT_MAX_MESSAGES, RATE_LIMIT_WINDOW_SECONDS, IMAGE_MAX_BYTES, DOCUMENT_MAX_BYTES and DOCUMENT_MAX_CHARS must be integers, and OLLAMA_USE_CHAT_API must be a boolean"
        ) from error

    if request_timeout_seconds < 5:
        raise ValueError("REQUEST_TIMEOUT_SECONDS must be >= 5")
    if max_context_messages < 1:
        raise ValueError("MAX_CONTEXT_MESSAGES must be >= 1")
    if rate_limit_max_messages < 0:
        raise ValueError("RATE_LIMIT_MAX_MESSAGES must be >= 0")
    if rate_limit_window_seconds < 1:
        raise ValueError("RATE_LIMIT_WINDOW_SECONDS must be >= 1")
    if image_max_bytes < 1024:
        raise ValueError("IMAGE_MAX_BYTES must be >= 1024")
    if document_max_bytes < 1024:
        raise ValueError("DOCUMENT_MAX_BYTES must be >= 1024")
    if document_max_chars < 1000:
        raise ValueError("DOCUMENT_MAX_CHARS must be >= 1000")
    if not ollama_keep_alive:
        raise ValueError("OLLAMA_KEEP_ALIVE cannot be empty")
    if not ollama_auth_scheme:
        raise ValueError("OLLAMA_AUTH_SCHEME cannot be empty")
    if not bot_default_locale:
        raise ValueError("BOT_DEFAULT_LOCALE cannot be empty")

    allowed_user_ids = _parse_allowed_user_ids(_require_env("ALLOWED_USER_IDS"))

    return Settings(
        telegram_bot_token=_require_env("TELEGRAM_BOT_TOKEN"),
        ollama_base_url=_require_env("OLLAMA_BASE_URL").rstrip("/"),
        ollama_api_key=ollama_api_key,
        ollama_auth_scheme=ollama_auth_scheme,
        ollama_default_model=_require_env("OLLAMA_DEFAULT_MODEL"),
        ollama_use_chat_api=ollama_use_chat_api,
        ollama_keep_alive=ollama_keep_alive,
        model_prefs_db_path=os.getenv("MODEL_PREFS_DB_PATH", "./data/bot.db").strip(),
        allowed_user_ids=allowed_user_ids,
        request_timeout_seconds=request_timeout_seconds,
        max_context_messages=max_context_messages,
        rate_limit_max_messages=rate_limit_max_messages,
        rate_limit_window_seconds=rate_limit_window_seconds,
        image_max_bytes=image_max_bytes,
        document_max_bytes=document_max_bytes,
        document_max_chars=document_max_chars,
        bot_default_locale=bot_default_locale,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
