from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    ollama_base_url: str
    ollama_default_model: str
    model_prefs_db_path: str
    allowed_user_ids: tuple[int, ...]
    request_timeout_seconds: int
    max_context_messages: int
    rate_limit_max_messages: int
    rate_limit_window_seconds: int
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


def load_settings() -> Settings:
    timeout_raw = os.getenv("REQUEST_TIMEOUT_SECONDS", "60").strip()
    max_context_raw = os.getenv("MAX_CONTEXT_MESSAGES", "12").strip()
    rate_limit_max_raw = os.getenv("RATE_LIMIT_MAX_MESSAGES", "0").strip()
    rate_limit_window_raw = os.getenv("RATE_LIMIT_WINDOW_SECONDS", "30").strip()

    try:
        request_timeout_seconds = int(timeout_raw)
        max_context_messages = int(max_context_raw)
        rate_limit_max_messages = int(rate_limit_max_raw)
        rate_limit_window_seconds = int(rate_limit_window_raw)
    except ValueError as error:
        raise ValueError(
            "REQUEST_TIMEOUT_SECONDS, MAX_CONTEXT_MESSAGES, RATE_LIMIT_MAX_MESSAGES and RATE_LIMIT_WINDOW_SECONDS must be integers"
        ) from error

    if request_timeout_seconds < 5:
        raise ValueError("REQUEST_TIMEOUT_SECONDS must be >= 5")
    if max_context_messages < 1:
        raise ValueError("MAX_CONTEXT_MESSAGES must be >= 1")
    if rate_limit_max_messages < 0:
        raise ValueError("RATE_LIMIT_MAX_MESSAGES must be >= 0")
    if rate_limit_window_seconds < 1:
        raise ValueError("RATE_LIMIT_WINDOW_SECONDS must be >= 1")

    allowed_user_ids = _parse_allowed_user_ids(_require_env("ALLOWED_USER_IDS"))

    return Settings(
        telegram_bot_token=_require_env("TELEGRAM_BOT_TOKEN"),
        ollama_base_url=_require_env("OLLAMA_BASE_URL").rstrip("/"),
        ollama_default_model=_require_env("OLLAMA_DEFAULT_MODEL"),
        model_prefs_db_path=os.getenv("MODEL_PREFS_DB_PATH", "./data/bot.db").strip(),
        allowed_user_ids=allowed_user_ids,
        request_timeout_seconds=request_timeout_seconds,
        max_context_messages=max_context_messages,
        rate_limit_max_messages=rate_limit_max_messages,
        rate_limit_window_seconds=rate_limit_window_seconds,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
