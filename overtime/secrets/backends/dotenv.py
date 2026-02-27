"""DotEnv file secret backend."""

import logging
from pathlib import Path
from typing import Optional

import dotenv

from ..base import SecretBackend

logger = logging.getLogger(__name__)


class DotEnvBackend(SecretBackend):
    """
    Read and write secrets to a .env file.

    Uses python-dotenv for parsing and writing. The .env file is a simple
    key=value format, one entry per line. Comments (# ...) are supported.

    Default file: .env in the current working directory.
    Configurable via the dotenv_path parameter.
    """

    def __init__(self, dotenv_path: Optional[str] = None):
        """
        Initialize DotEnv backend.

        Args:
            dotenv_path: Path to .env file (default: .env in cwd)
        """
        self.dotenv_path = Path(dotenv_path) if dotenv_path else Path.cwd() / '.env'
        logger.debug(f"DotEnv backend using: {self.dotenv_path}")

    def _ensure_file(self) -> None:
        """Create .env file with secure permissions if it doesn't exist."""
        if not self.dotenv_path.exists():
            self.dotenv_path.parent.mkdir(parents=True, exist_ok=True)
            self.dotenv_path.touch(mode=0o600)
            logger.info(f"Created {self.dotenv_path}")

    def get_secret(self, key: str) -> Optional[str]:
        """Get secret from .env file."""
        if not self.dotenv_path.exists():
            return None

        values = dotenv.dotenv_values(str(self.dotenv_path))
        value = values.get(key)

        if not value:
            return None

        logger.debug(f"Retrieved secret '{key}' from {self.dotenv_path}")
        return value

    def set_secret(self, key: str, value: str) -> None:
        """Store secret in .env file."""
        self._ensure_file()
        dotenv.set_key(str(self.dotenv_path), key, value)
        logger.info(f"Stored secret '{key}' in {self.dotenv_path}")

    def delete_secret(self, key: str) -> None:
        """Delete secret from .env file."""
        if not self.dotenv_path.exists():
            logger.warning(f"Secret '{key}' not found — .env file does not exist")
            return

        values = dotenv.dotenv_values(str(self.dotenv_path))
        if key in values:
            dotenv.unset_key(str(self.dotenv_path), key)
            logger.info(f"Deleted secret '{key}' from {self.dotenv_path}")
        else:
            logger.warning(f"Secret '{key}' not found in {self.dotenv_path}")

    def list_secrets(self) -> list[str]:
        """List all secret keys in .env file."""
        if not self.dotenv_path.exists():
            return []

        values = dotenv.dotenv_values(str(self.dotenv_path))
        return sorted(values.keys())

    def backend_name(self) -> str:
        """Backend name."""
        return f"DotEnv ({self.dotenv_path})"
