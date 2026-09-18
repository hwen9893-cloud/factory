"""Desktop logging with bounded UTF-8 files."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_file_logging(
    path: Path,
    *,
    level: int = logging.INFO,
    max_bytes: int = 2 * 1024 * 1024,
    backup_count: int = 3,
) -> RotatingFileHandler:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(level)
    for existing in tuple(root.handlers):
        if isinstance(existing, RotatingFileHandler) and Path(existing.baseFilename) == path.resolve():
            return existing
    root.addHandler(handler)
    logging.captureWarnings(True)
    return handler

