from __future__ import annotations

import logging
import re
import sys
import time


class SecretFilter(logging.Filter):
    """Redact sensitive values (API keys, tokens) from log records."""

    _PATTERNS = (
        re.compile(r"(Bearer\s+)\S+", re.IGNORECASE),
        re.compile(r"(api[_-]?key[=:]\s*)\S+", re.IGNORECASE),
        re.compile(r"(token[=:]\s*)\S+", re.IGNORECASE),
        re.compile(r"(Authorization[=:]\s*)\S+", re.IGNORECASE),
    )

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for pattern in self._PATTERNS:
            msg = pattern.sub(r"\1***", msg)
        record.msg = msg
        record.args = None
        return True


def configure_logging(level: str) -> None:
    logging.Formatter.converter = time.gmtime

    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)sZ | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )

    logging.getLogger().addFilter(SecretFilter())
    logging.captureWarnings(True)
