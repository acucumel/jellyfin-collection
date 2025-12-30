"""Logging configuration using Loguru."""

import sys
from pathlib import Path
from typing import Optional

from loguru import logger


def setup_logging(
    level: str = "INFO",
    log_dir: Optional[Path] = None,
    json_logs: bool = False,
) -> None:
    """
    Configure application logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Directory for log files (optional)
        json_logs: Use JSON format for file logs
    """
    # Remove default handler
    logger.remove()

    # Console handler with colors
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    logger.add(
        sys.stderr,
        format=log_format,
        level=level,
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    # File handlers if log_dir is specified
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)

        # Main log file with rotation (with ANSI colors for terminal viewing)
        colored_file_format = (
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        )

        # Plain format for JSON logs
        plain_file_format = (
            "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
            "{name}:{function}:{line} | {message}"
        )

        if json_logs:
            logger.add(
                log_dir / "jfc.log",
                format=plain_file_format,
                level=level,
                rotation="10 MB",
                retention="7 days",
                compression="gz",
                serialize=True,
            )
        else:
            logger.add(
                log_dir / "jfc.log",
                format=colored_file_format,
                level=level,
                rotation="10 MB",
                retention="7 days",
                compression="gz",
                colorize=True,
            )

        # Separate error log (plain format for easier parsing)
        logger.add(
            log_dir / "error.log",
            format=plain_file_format,
            level="ERROR",
            rotation="10 MB",
            retention="30 days",
            compression="gz",
        )

    logger.info(f"Logging configured with level: {level}")


def get_logger(name: str) -> "logger":
    """
    Get a logger instance for a module.

    Args:
        name: Module name (typically __name__)

    Returns:
        Logger instance bound to the module name
    """
    return logger.bind(name=name)


# Convenience functions for structured logging
def log_collection_update(
    collection_name: str,
    library: str,
    added: int = 0,
    removed: int = 0,
    total: int = 0,
) -> None:
    """Log collection update with structured data."""
    logger.info(
        f"Collection '{collection_name}' updated in '{library}': "
        f"+{added} -{removed} = {total} items"
    )


def log_provider_request(provider: str, endpoint: str, params: dict | None = None) -> None:
    """Log provider API request."""
    logger.debug(f"[{provider}] Request: {endpoint} | Params: {params}")


def log_media_action(
    action: str,
    title: str,
    year: Optional[int] = None,
    tmdb_id: Optional[int] = None,
    destination: Optional[str] = None,
) -> None:
    """Log media action (add, remove, match, etc.)."""
    year_str = f" ({year})" if year else ""
    tmdb_str = f" [tmdb:{tmdb_id}]" if tmdb_id else ""
    dest_str = f" -> {destination}" if destination else ""
    logger.info(f"[{action.upper()}] {title}{year_str}{tmdb_str}{dest_str}")
