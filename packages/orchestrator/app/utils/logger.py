"""
Pulse Orchestrator — Structured Logger

Sets up a consistent logging format across all modules.
Every log line includes timestamp, level, module name, and message.
"""

import logging
import sys
import io

from app.config import settings


def setup_logger(name: str = "pulse") -> logging.Logger:
    """
    Create a logger with a clean, readable format.

    Usage:
        from app.utils.logger import setup_logger
        logger = setup_logger(__name__)
        logger.info("Something happened", extra={"pr": 42})
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers if called multiple times
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    # Console handler with structured format
    # Force UTF-8 output on Windows to support emojis in log messages
    utf8_stream = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    handler = logging.StreamHandler(utf8_stream)
    handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)-25s | %(message)s",
        datefmt="%H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger
