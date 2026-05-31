"""Logging setup with rotating file handler and console output."""

import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logger(log_dir: str = None, level: int = logging.DEBUG) -> logging.Logger:
    """Configure and return the application logger."""
    if log_dir is None:
        log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "logs")
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger("live_recorder")
    logger.setLevel(level)

    # Avoid duplicate handlers on repeated calls
    if logger.handlers:
        return logger

    # Rotating file handler: 10MB per file, keep 5 backups
    fh = RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)-5s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    logger.addHandler(fh)
    logger.addHandler(ch)

    return logger
