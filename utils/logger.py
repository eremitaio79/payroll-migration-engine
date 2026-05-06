from __future__ import annotations

import logging
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler


console = Console()


def setup_logger(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("etl_migra_cc")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    handler = RichHandler(console=console, rich_tracebacks=True, show_path=False)
    handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)

    Path("reports/logs").mkdir(parents=True, exist_ok=True)
    return logger
