from __future__ import annotations

import logging

try:
    from rich.console import Console
    from rich.logging import RichHandler
except ImportError:  # pragma: no cover - fallback path
    Console = None
    RichHandler = None


def get_console():
    if Console is None:
        return None
    return Console()


def get_logger(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("webinfo2md")
    if logger.handlers:
        logger.setLevel(logging.DEBUG if verbose else logging.INFO)
        return logger

    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    if RichHandler is not None:
        handler = RichHandler(show_path=False, markup=True)
    else:  # pragma: no cover - fallback path
        handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger
