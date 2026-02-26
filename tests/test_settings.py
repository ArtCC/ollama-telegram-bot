import pytest

from src.config.settings import load_settings


@pytest.fixture(autouse=True)
def base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama:11434")
    monkeypatch.setenv("OLLAMA_DEFAULT_MODEL", "llama3.2")
    monkeypatch.setenv("ALLOWED_USER_IDS", "123")


def test_load_settings_parses_allowed_user_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOWED_USER_IDS", "123, 456,123")

    settings = load_settings()

    assert settings.allowed_user_ids == (123, 456)


def test_load_settings_rejects_invalid_allowed_user_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOWED_USER_IDS", "123,abc")

    with pytest.raises(ValueError, match="ALLOWED_USER_IDS"):
        load_settings()


def test_load_settings_rejects_empty_allowed_user_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOWED_USER_IDS", "   ")

    with pytest.raises(ValueError, match="ALLOWED_USER_IDS"):
        load_settings()


def test_load_settings_rejects_negative_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_MAX_MESSAGES", "-1")

    with pytest.raises(ValueError, match="RATE_LIMIT_MAX_MESSAGES"):
        load_settings()


def test_load_settings_accepts_rate_limit_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_MAX_MESSAGES", "0")

    settings = load_settings()

    assert settings.rate_limit_max_messages == 0


def test_load_settings_rejects_invalid_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "0")

    with pytest.raises(ValueError, match="RATE_LIMIT_WINDOW_SECONDS"):
        load_settings()


def test_load_settings_parses_rate_limit_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_MAX_MESSAGES", "5")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "45")

    settings = load_settings()

    assert settings.rate_limit_max_messages == 5
    assert settings.rate_limit_window_seconds == 45


def test_load_settings_chat_api_defaults() -> None:
    settings = load_settings()

    assert settings.ollama_use_chat_api is True
    assert settings.ollama_keep_alive == "5m"


def test_load_settings_rejects_invalid_chat_api_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_USE_CHAT_API", "maybe")

    with pytest.raises(ValueError, match="OLLAMA_USE_CHAT_API"):
        load_settings()


def test_load_settings_rejects_empty_keep_alive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "   ")

    with pytest.raises(ValueError, match="OLLAMA_KEEP_ALIVE"):
        load_settings()


def test_load_settings_image_max_bytes_default() -> None:
    settings = load_settings()

    assert settings.image_max_bytes == 5 * 1024 * 1024


def test_load_settings_rejects_too_small_image_max_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMAGE_MAX_BYTES", "100")

    with pytest.raises(ValueError, match="IMAGE_MAX_BYTES"):
        load_settings()


def test_load_settings_default_locale_default_value() -> None:
    settings = load_settings()

    assert settings.bot_default_locale == "en"


def test_load_settings_rejects_empty_default_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_DEFAULT_LOCALE", "   ")

    with pytest.raises(ValueError, match="BOT_DEFAULT_LOCALE"):
        load_settings()


def test_load_settings_cloud_auth_defaults() -> None:
    settings = load_settings()

    assert settings.ollama_api_key is None
    assert settings.ollama_auth_scheme == "Bearer"


def test_load_settings_cloud_auth_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_API_KEY", "abc123")
    monkeypatch.setenv("OLLAMA_AUTH_SCHEME", "Token")

    settings = load_settings()

    assert settings.ollama_api_key == "abc123"
    assert settings.ollama_auth_scheme == "Token"


def test_load_settings_rejects_invalid_document_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCUMENT_MAX_BYTES", "100")

    with pytest.raises(ValueError, match="DOCUMENT_MAX_BYTES"):
        load_settings()


def test_load_settings_document_limits_defaults() -> None:
    settings = load_settings()

    assert settings.document_max_bytes == 10 * 1024 * 1024
    assert settings.document_max_chars == 12000
