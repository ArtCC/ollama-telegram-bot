from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    ollama_base_url: str
    ollama_default_model: str
    model_prefs_db_path: str
    request_timeout_seconds: int
    max_context_messages: int
    log_level: str


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def load_settings() -> Settings:
    timeout_raw = os.getenv("REQUEST_TIMEOUT_SECONDS", "60").strip()
    max_context_raw = os.getenv("MAX_CONTEXT_MESSAGES", "12").strip()

    try:
        request_timeout_seconds = int(timeout_raw)
        max_context_messages = int(max_context_raw)
    except ValueError as error:
        raise ValueError("REQUEST_TIMEOUT_SECONDS and MAX_CONTEXT_MESSAGES must be integers") from error

    if request_timeout_seconds < 5:
        raise ValueError("REQUEST_TIMEOUT_SECONDS must be >= 5")
    if max_context_messages < 1:
        raise ValueError("MAX_CONTEXT_MESSAGES must be >= 1")

    return Settings(
        telegram_bot_token=_require_env("TELEGRAM_BOT_TOKEN"),
        ollama_base_url=_require_env("OLLAMA_BASE_URL").rstrip("/"),
        ollama_default_model=_require_env("OLLAMA_DEFAULT_MODEL"),
        model_prefs_db_path=os.getenv("MODEL_PREFS_DB_PATH", "./data/bot.db").strip(),
        request_timeout_seconds=request_timeout_seconds,
        max_context_messages=max_context_messages,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
