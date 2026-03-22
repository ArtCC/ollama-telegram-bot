"""Tests for i18n pluralization and new features."""

from __future__ import annotations

import json
from pathlib import Path

from src.i18n import I18nService


def _write_locale(base_dir: Path, locale: str, payload: dict) -> None:
    (base_dir / f"{locale}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_pluralization_one(tmp_path: Path) -> None:
    _write_locale(tmp_path, "en", {
        "items": {
            "count": {
                "one": "{count} item",
                "other": "{count} items",
            }
        }
    })
    i18n = I18nService(locales_dir=tmp_path, default_locale="en")

    assert i18n.t("items.count", count=1) == "1 item"


def test_pluralization_other(tmp_path: Path) -> None:
    _write_locale(tmp_path, "en", {
        "items": {
            "count": {
                "one": "{count} item",
                "other": "{count} items",
            }
        }
    })
    i18n = I18nService(locales_dir=tmp_path, default_locale="en")

    assert i18n.t("items.count", count=0) == "0 items"
    assert i18n.t("items.count", count=5) == "5 items"


def test_pluralization_fallback_to_default_locale(tmp_path: Path) -> None:
    _write_locale(tmp_path, "en", {
        "items": {
            "count": {
                "one": "{count} item",
                "other": "{count} items",
            }
        }
    })
    _write_locale(tmp_path, "fr", {"other_key": "bonjour"})
    i18n = I18nService(locales_dir=tmp_path, default_locale="en")

    # French doesn't have the plural keys, should fallback to English
    assert i18n.t("items.count", locale="fr", count=3) == "3 items"


def test_pluralization_missing_plural_keys_uses_base_key(tmp_path: Path) -> None:
    _write_locale(tmp_path, "en", {
        "items": {
            "count": "Total: {count}"
        }
    })
    i18n = I18nService(locales_dir=tmp_path, default_locale="en")

    # No .one/.other keys, should fall through to the base key
    assert i18n.t("items.count", count=5) == "Total: 5"


def test_pluralization_without_count_kwarg(tmp_path: Path) -> None:
    _write_locale(tmp_path, "en", {
        "items": {
            "count": {
                "one": "{count} item",
                "other": "{count} items",
            }
        }
    })
    i18n = I18nService(locales_dir=tmp_path, default_locale="en")

    # Without count kwarg, no pluralization attempted — base key maps to a dict,
    # which _lookup returns as a string representation (non-string value warning)
    result = i18n.t("items.count")
    # The dict value is returned as str, not the missing-key marker
    assert "item" in result
