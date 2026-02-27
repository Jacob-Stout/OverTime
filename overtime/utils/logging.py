"""Logging configuration for OverTime."""

import logging
import sys


class ColoredFormatter(logging.Formatter):
    """Formatter with colored log levels."""

    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
    }
    RESET = '\033[0m'

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors."""
        # Add color to level name
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{self.RESET}"

        return super().format(record)


def setup_logging(level: str = 'INFO', verbose: bool = False) -> None:
    """
    Configure logging for OverTime.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        verbose: If True, show module names and line numbers
    """
    if verbose:
        log_format = '%(levelname)s | %(name)s:%(lineno)d | %(message)s'
    else:
        log_format = '%(levelname)s | %(message)s'

    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ColoredFormatter(log_format))

    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        handlers=[handler],
        force=True  # Override any existing configuration
    )

    # Suppress noisy third-party loggers
    logging.getLogger('paramiko').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
