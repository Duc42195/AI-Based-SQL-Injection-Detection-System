"""Centralised logging setup.

Production code uses the stdlib ``logging`` module (never ``print``). Long
running steps (train, retrain, benchmark) should log clear progress via the
logger returned by :func:`get_logger`.
"""

from __future__ import annotations

import logging
import sys

_DEFAULT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_CONFIGURED = False


def setup_logging(level: str = "INFO", fmt: str = _DEFAULT_FORMAT) -> None:
    """Configure the root logger once for the whole process.

    Args:
        level: Logging level name, e.g. ``"INFO"`` or ``"DEBUG"``.
        fmt: Log record format string.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt))
    root = logging.getLogger()
    root.setLevel(level.upper())
    root.addHandler(handler)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a module logger, initialising logging on first use.

    Args:
        name: Logger name, conventionally ``__name__`` of the caller.

    Returns:
        A configured :class:`logging.Logger` instance.
    """
    if not _CONFIGURED:
        setup_logging()
    return logging.getLogger(name)
