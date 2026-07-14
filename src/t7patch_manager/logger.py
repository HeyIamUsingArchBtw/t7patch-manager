"""Central logging for the app — writes to stderr and to a log file.

The log file lives in ~/.config/t7patch-manager/t7patch-manager.log
and is shown in the Debug Log dialog.
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from .paths import log_file

_configured = False


def configure() -> logging.Logger:
    """Set up root logging once; safe to call multiple times."""
    global _configured
    logger = logging.getLogger("t7patch")
    if _configured:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # Console — INFO+
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(console)

    # Rotating file — DEBUG+
    try:
        path = log_file()
        fh = RotatingFileHandler(path, maxBytes=256_000, backupCount=1, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(fh)
    except OSError as e:  # noqa: BLE001
        logger.warning("Could not open log file: %s", e)

    _configured = True
    return logger
