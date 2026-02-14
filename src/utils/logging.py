from __future__ import annotations

import logging
import sys
import time


def configure_logging(level: str) -> None:
    logging.Formatter.converter = time.gmtime

    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)sZ | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )

    logging.captureWarnings(True)
