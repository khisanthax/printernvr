from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def ensure_directories(paths: list[str]) -> None:
    for path in paths:
        Path(path).mkdir(parents=True, exist_ok=True)


def configure_logging(log_dir: str, log_level: str = "INFO") -> None:
    ensure_directories([log_dir])

    level = getattr(logging, log_level.upper(), logging.INFO)
    logger = logging.getLogger()
    logger.setLevel(level)

    if logger.handlers:
        return

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        Path(log_dir) / "printernvr.log",
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(stream_handler)
    logger.addHandler(file_handler)
