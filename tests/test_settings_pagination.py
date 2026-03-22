"""Tests for new Settings fields: pagination sizes."""

from __future__ import annotations

import pytest

from src.config.settings import load_settings


@pytest.fixture(autouse=True)
def base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama:11434")
    monkeypatch.setenv("OLLAMA_DEFAULT_MODEL", "llama3.2")
    monkeypatch.setenv("ALLOWED_USER_IDS", "123")


def test_pagination_defaults() -> None:
    settings = load_settings()
    assert settings.models_page_size == 8
    assert settings.web_models_page_size == 8
    assert settings.files_page_size == 6


def test_pagination_custom_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODELS_PAGE_SIZE", "12")
    monkeypatch.setenv("WEB_MODELS_PAGE_SIZE", "10")
    monkeypatch.setenv("FILES_PAGE_SIZE", "4")

    settings = load_settings()

    assert settings.models_page_size == 12
    assert settings.web_models_page_size == 10
    assert settings.files_page_size == 4


def test_pagination_rejects_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODELS_PAGE_SIZE", "0")

    with pytest.raises(ValueError, match="MODELS_PAGE_SIZE"):
        load_settings()


def test_pagination_rejects_negative(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FILES_PAGE_SIZE", "-1")

    with pytest.raises(ValueError, match="FILES_PAGE_SIZE"):
        load_settings()
