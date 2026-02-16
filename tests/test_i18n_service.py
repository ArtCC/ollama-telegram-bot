from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.i18n import I18nService


def _write_locale(base_dir: Path, locale: str, payload: dict[str, object]) -> None:
    (base_dir / f"{locale}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_i18n_resolve_locale_prefers_exact_and_base(tmp_path: Path) -> None:
    _write_locale(tmp_path, "en", {"a": {"b": "EN"}})
    _write_locale(tmp_path, "es", {"a": {"b": "ES"}})

    i18n = I18nService(locales_dir=tmp_path, default_locale="en")

    assert i18n.resolve_locale("es") == "es"
    assert i18n.resolve_locale("es-ES") == "es"
    assert i18n.resolve_locale("fr") == "en"


def test_i18n_translate_with_format_and_fallback(tmp_path: Path) -> None:
    _write_locale(tmp_path, "en", {"greet": {"hello": "Hello {name}"}})

    i18n = I18nService(locales_dir=tmp_path, default_locale="en")

    assert i18n.t("greet.hello", locale="fr", name="Arturo") == "Hello Arturo"


def test_i18n_missing_key_returns_marker(tmp_path: Path) -> None:
    _write_locale(tmp_path, "en", {"greet": {"hello": "Hello"}})

    i18n = I18nService(locales_dir=tmp_path, default_locale="en")

    assert i18n.t("greet.goodbye", locale="en") == "[[greet.goodbye]]"


def test_i18n_validate_required_keys_raises_for_missing(tmp_path: Path) -> None:
    _write_locale(tmp_path, "en", {"a": {"b": "x"}})

    i18n = I18nService(locales_dir=tmp_path, default_locale="en")

    with pytest.raises(ValueError, match="Missing required i18n keys"):
        i18n.validate_required_keys(["a.b", "a.c"])


def test_i18n_validate_locale_completeness_against_default(tmp_path: Path) -> None:
    _write_locale(tmp_path, "en", {"a": {"b": "x", "c": "y"}})
    _write_locale(tmp_path, "es", {"a": {"b": "z"}})

    i18n = I18nService(locales_dir=tmp_path, default_locale="en")

    with pytest.raises(ValueError, match="missing keys"):
        i18n.validate_required_keys(["a.b"])
