from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)


class I18nService:
    def __init__(self, locales_dir: Path, default_locale: str = "en") -> None:
        self._locales_dir = locales_dir
        self._default_locale = self._normalize_locale(default_locale)
        self._translations = self._load_locales(locales_dir)

        if self._default_locale not in self._translations:
            raise ValueError(f"Default locale '{self._default_locale}' was not found in {locales_dir}")

    @property
    def default_locale(self) -> str:
        return self._default_locale

    @property
    def available_locales(self) -> tuple[str, ...]:
        return tuple(sorted(self._translations.keys()))

    def resolve_locale(self, user_language_code: str | None) -> str:
        if not user_language_code:
            return self._default_locale

        normalized = self._normalize_locale(user_language_code)
        if normalized in self._translations:
            return normalized

        if "-" in normalized:
            base = normalized.split("-", 1)[0]
            if base in self._translations:
                return base

        return self._default_locale

    def t(self, key: str, locale: str | None = None, **kwargs: Any) -> str:
        preferred_locale = self.resolve_locale(locale)

        template = self._lookup(self._translations.get(preferred_locale, {}), key)
        if template is None and preferred_locale != self._default_locale:
            template = self._lookup(self._translations.get(self._default_locale, {}), key)

        if template is None:
            logger.warning("i18n_missing_key key=%s locale=%s", key, preferred_locale)
            return f"[[{key}]]"

        if not isinstance(template, str):
            logger.warning("i18n_non_string_value key=%s locale=%s", key, preferred_locale)
            return str(template)

        if kwargs:
            try:
                return template.format(**kwargs)
            except KeyError as error:
                logger.warning(
                    "i18n_format_missing_arg key=%s locale=%s missing=%s",
                    key,
                    preferred_locale,
                    error,
                )
        return template

    def validate_required_keys(self, required_keys: Iterable[str]) -> None:
        default_keys = self._flatten_keys(self._translations[self._default_locale])
        missing_in_default = sorted(set(required_keys) - default_keys)
        if missing_in_default:
            joined = ", ".join(missing_in_default)
            raise ValueError(f"Missing required i18n keys in default locale '{self._default_locale}': {joined}")

        for locale, payload in self._translations.items():
            locale_keys = self._flatten_keys(payload)
            missing = sorted(default_keys - locale_keys)
            if missing:
                joined = ", ".join(missing[:10])
                suffix = "..." if len(missing) > 10 else ""
                raise ValueError(f"Locale '{locale}' is missing keys from default locale: {joined}{suffix}")

    @staticmethod
    def _normalize_locale(value: str) -> str:
        return value.strip().replace("_", "-").lower()

    def _load_locales(self, locales_dir: Path) -> dict[str, dict[str, Any]]:
        if not locales_dir.exists() or not locales_dir.is_dir():
            raise ValueError(f"Locales directory not found: {locales_dir}")

        translations: dict[str, dict[str, Any]] = {}
        for file in sorted(locales_dir.glob("*.json")):
            locale = self._normalize_locale(file.stem)
            with file.open("r", encoding="utf-8") as handle:
                parsed = json.load(handle)
            if not isinstance(parsed, dict):
                raise ValueError(f"Locale file must contain a JSON object: {file}")
            translations[locale] = parsed

        if not translations:
            raise ValueError(f"No locale JSON files found in: {locales_dir}")

        return translations

    @staticmethod
    def _lookup(data: dict[str, Any], dotted_key: str) -> Any | None:
        current: Any = data
        for part in dotted_key.split("."):
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return current

    @classmethod
    def _flatten_keys(cls, data: dict[str, Any], prefix: str = "") -> set[str]:
        flattened: set[str] = set()
        for key, value in data.items():
            current = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                flattened.update(cls._flatten_keys(value, current))
            else:
                flattened.add(current)
        return flattened
